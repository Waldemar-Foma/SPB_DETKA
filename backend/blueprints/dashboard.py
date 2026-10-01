from flask import Blueprint, redirect, render_template, request, url_for
from backend.models import Procurement
from backend.services.auth import current_user, login_required

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

@bp.get("/")
@login_required
def page():
    user = current_user()
    if user.account_role == "admin":
        return redirect(url_for("admin.page"))
    number = (request.args.get("procurement") or "").strip()
    if not number:
        return redirect(url_for("contracts.page"))
    procurement = Procurement.query.filter_by(procurement_number=number, source_system="USER", customer_inn=user.organization_inn).first()
    if not procurement or procurement.deleted_at:
        return redirect(url_for("contracts.page"))

    # Подбор доступен только пока заказчик ещё никого не выбрал.
    # После выбора, завершения или архива прямой URL /dashboard/ тоже не открывает карту.
    if procurement.selected_supplier_inn or procurement.status != "matching" or procurement.completed_at or procurement.archived_at:
        return redirect(url_for("contracts.detail", number=procurement.procurement_number))

    response = render_template("pages/dashboard.html", page_id="dashboard", page_title="Подбор исполнителя")
    return response
