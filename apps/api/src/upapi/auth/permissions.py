"""Rollar va ruxsatlar matritsasi (03-arxitektura.md §10, M1). Server tomonda har endpoint shu orqali tekshiriladi."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    ACCOUNTANT = "accountant"
    WAREHOUSE = "warehouse"


class Permission(StrEnum):
    VIEW_FINANCE = "view_finance"  # foyda, tannarx, pul oqimi
    VIEW_PURCHASES = "view_purchases"  # xarid, ombor, postavka
    MANAGE_PURCHASES = "manage_purchases"
    VIEW_PURCHASE_AMOUNTS = "view_purchase_amounts"  # omborchi summalarni ko'rmaydi
    VIEW_SETTINGS = "view_settings"  # xarajat, soliq, sozlamalar
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_ACCOUNTS = "manage_accounts"  # marketplace kaliti
    MANAGE_MEMBERS = "manage_members"
    MANAGE_BILLING = "manage_billing"
    DELETE_ORG = "delete_org"
    VIEW_AUDIT = "view_audit"
    EXPORT = "export"
    EXPORT_INVENTORY = "export_inventory"


P = Permission
_READ_ALL = {P.VIEW_FINANCE, P.VIEW_PURCHASES, P.VIEW_PURCHASE_AMOUNTS, P.VIEW_SETTINGS}
_EXPORT = {P.EXPORT, P.EXPORT_INVENTORY}

MATRIX: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.MANAGER: frozenset(_READ_ALL | _EXPORT | {P.MANAGE_PURCHASES, P.MANAGE_SETTINGS}),
    Role.ACCOUNTANT: frozenset(_READ_ALL | _EXPORT),
    Role.WAREHOUSE: frozenset({P.VIEW_PURCHASES, P.MANAGE_PURCHASES, P.EXPORT_INVENTORY}),
}


def allowed(role: Role, permission: Permission) -> bool:
    return permission in MATRIX[role]
