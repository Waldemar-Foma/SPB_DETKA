"""Главный пользовательский контур: заявки заказчика."""
from __future__ import annotations

import re
import secrets
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from backend.extensions import db
from backend.models import Procurement, Supplier, SupplierReview
from backend.services.analysis_helpers import analyse_text, extract_upload
from backend.services.auth import current_user, login_required
from backend.services.reputation import enrich_contacts_from_web, invalidate_review_cache, invalidate_workload_cache
from backend.services.request_lifecycle import archive_stale_requests, touch
from backend.services.role_classifier import procurement_kind

bp = Blueprint("contracts", __name__, url_prefix="/contracts")

STATUS_LABELS = {
    "matching": "Ищем исполнителя",
    "selected": "Исполнитель выбран",
    "completed": "Заказ завершён",
    "archived": "В архиве",
}


def _owned_or_404(number: str) -> Procurement:
    user = current_user()
    q = Procurement.query.filter_by(procurement_number=number, source_system="USER").filter(Procurement.deleted_at.is_(None))
    if user.account_role != "admin":
        q = q.filter_by(customer_inn=user.organization_inn)
    return q.first_or_404()


@bp.get("/")
@login_required
def page():
    user = current_user()
    if user.account_role == "admin":
        return redirect(url_for("admin.page"))
    archive_stale_requests(user.organization_inn)
    active = Procurement.query.filter(
        Procurement.source_system == "USER",
        Procurement.customer_inn == user.organization_inn,
        Procurement.deleted_at.is_(None),
        Procurement.archived_at.is_(None),
    ).order_by(Procurement.updated_at.desc()).all()
    archived = Procurement.query.filter(
        Procurement.source_system == "USER",
        Procurement.customer_inn == user.organization_inn,
        Procurement.deleted_at.is_(None),
        Procurement.archived_at.isnot(None),
    ).order_by(Procurement.archived_at.desc()).limit(50).all()
    selected_inns = {p.selected_supplier_inn for p in active + archived if p.selected_supplier_inn}
    names = {s.inn: s.name for s in Supplier.query.filter(Supplier.inn.in_(selected_inns)).all()} if selected_inns else {}
    return render_template(
        "pages/contracts.html",
        page_id="requests",
        page_title="Мои заявки",
        active=active,
        archived=archived,
        supplier_names=names,
        status_labels=STATUS_LABELS,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_request():
    user = current_user()
    if user.account_role != "customer":
        return redirect(url_for("contracts.page"))

    error = None
    values = {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "initial_price": request.form.get("initial_price", "").strip(),
        "delivery_region": request.form.get("delivery_region", "Санкт-Петербург").strip() or "Санкт-Петербург",
        "okpd2": request.form.get("okpd2", "").strip(),
    }
    mode = request.form.get("mode", request.args.get("mode", ""))

    if request.method == "POST":
        try:
            if mode == "spec":
                upload = request.files.get("file")
                pasted = request.form.get("spec_text", "").strip()
                if upload and upload.filename:
                    text = extract_upload(upload)
                    analysed = analyse_text(text, upload.filename)
                elif pasted:
                    analysed = analyse_text(pasted, "вставленный текст")
                else:
                    raise ValueError("Загрузите ТЗ или вставьте его текст.")
                title = values["title"] or analysed["title"]
                subject = analysed["subject"]
                keywords = " ".join(analysed["keywords"])
                okpd2 = values["okpd2"] or (analysed["okpd2_candidates"][0] if analysed["okpd2_candidates"] else "AUTO")
                input_mode = "spec"
            else:
                title = values["title"]
                subject = values["description"]
                if len(title) < 3:
                    raise ValueError("Коротко назовите, что нужно заказать.")
                if len(subject) < 10:
                    raise ValueError("Опишите заказ чуть подробнее — это повысит качество подбора.")
                analysed = analyse_text(f"{title}\n{subject}", "описание заказчика")
                keywords = " ".join(analysed["keywords"])
                okpd2 = values["okpd2"] or (analysed["okpd2_candidates"][0] if analysed["okpd2_candidates"] else "AUTO")
                input_mode = "manual"

            price = _price(values["initial_price"])
            number = _request_number()
            proc = Procurement(
                procurement_number=number,
                title=title[:500],
                subject=subject[:12000],
                okpd2_code=okpd2,
                okpd2_name=title[:500],
                region=values["delivery_region"],
                delivery_region=values["delivery_region"],
                initial_price=price,
                keywords=keywords,
                customer_inn=user.organization_inn,
                source_system="USER",
                input_mode=input_mode,
                is_smp=False,
                publish_date=datetime.utcnow().date(),
                status="matching",
            )
            proc.procurement_kind = procurement_kind(proc)
            db.session.add(proc)
            db.session.commit()
            return redirect(url_for("dashboard.page", procurement=number))
        except Exception as exc:
            error = str(exc)

    return render_template(
        "pages/request_new.html",
        page_id="request-new",
        page_title="Новая заявка",
        mode=mode,
        values=values,
        error=error,
    )


@bp.get("/<number>")
@login_required
def detail(number: str):
    proc = _owned_or_404(number)
    archive_stale_requests(proc.customer_inn)
    supplier = Supplier.query.filter_by(inn=proc.selected_supplier_inn).first() if proc.selected_supplier_inn else None
    if supplier and proc.selected_supplier_inn:
        try:
            enrich_contacts_from_web(supplier)
        except Exception:
            pass
    user = current_user()
    review = SupplierReview.query.filter_by(procurement_id=proc.id, user_id=user.id).first()
    return render_template(
        "pages/request_detail.html",
        page_id="request-detail",
        page_title="Заявка",
        procurement=proc,
        supplier=supplier,
        review=review,
        status_labels=STATUS_LABELS,
    )


@bp.post("/<number>/complete")
@login_required
def complete(number: str):
    proc = _owned_or_404(number)
    if not proc.selected_supplier_inn:
        flash("Сначала выберите исполнителя.", "warning")
    else:
        proc.status = "completed"
        proc.completed_at = datetime.utcnow()
        touch(proc)
        db.session.commit()
        invalidate_workload_cache()
        flash("Заказ отмечен как завершённый. Теперь можно оставить отзыв.", "success")
    return redirect(url_for("contracts.detail", number=number))


@bp.post("/<number>/review")
@login_required
def add_review(number: str):
    proc = _owned_or_404(number)
    user = current_user()
    if proc.status != "completed" or not proc.selected_supplier_inn:
        flash("Отзыв можно оставить только после завершения заказа.", "warning")
        return redirect(url_for("contracts.detail", number=number))
    if SupplierReview.query.filter_by(procurement_id=proc.id, user_id=user.id).first():
        flash("Отзыв по этой заявке уже оставлен.", "warning")
        return redirect(url_for("contracts.detail", number=number))
    supplier = Supplier.query.filter_by(inn=proc.selected_supplier_inn).first_or_404()
    try:
        rating = _rating(request.form.get("rating"), required=True)
        review = SupplierReview(
            procurement_id=proc.id,
            supplier_id=supplier.id,
            user_id=user.id,
            rating=rating,
            quality_rating=_rating(request.form.get("quality_rating")),
            deadlines_rating=_rating(request.form.get("deadlines_rating")),
            communication_rating=_rating(request.form.get("communication_rating")),
            comment=(request.form.get("comment") or "").strip()[:4000],
        )
        db.session.add(review)
        touch(proc)
        db.session.commit()
        invalidate_review_cache()
        flash("Спасибо. Отзыв добавлен в метрики компании.", "success")
    except ValueError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("contracts.detail", number=number))


@bp.post("/<number>/delete")
@login_required
def delete(number: str):
    proc = _owned_or_404(number)
    proc.deleted_at = datetime.utcnow()
    proc.status = "deleted"
    touch(proc)
    db.session.commit()
    invalidate_workload_cache()
    flash("Заявка удалена из рабочего списка.", "success")
    return redirect(url_for("contracts.page"))


def _request_number() -> str:
    return f"REQ-{datetime.utcnow():%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def _price(value: str) -> float:
    cleaned = re.sub(r"[^0-9,.]", "", value or "").replace(",", ".")
    try:
        return max(0.0, float(cleaned)) if cleaned else 0.0
    except ValueError:
        return 0.0


def _rating(value, required: bool = False):
    if value in (None, ""):
        if required:
            raise ValueError("Поставьте общую оценку от 1 до 5.")
        return None
    n = int(value)
    if n < 1 or n > 5:
        raise ValueError("Оценка должна быть от 1 до 5.")
    return n
