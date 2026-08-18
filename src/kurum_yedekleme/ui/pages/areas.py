"""Yedekleme alanları ekranı."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.db.models import BackupArea, BackupHistoryRecord
from kurum_yedekleme.services.area_service import AreaError, AreaService
from kurum_yedekleme.ui.widgets.elided_path_label import ElidedPathLabel
from kurum_yedekleme.ui.widgets.page_header import PageHeader
from kurum_yedekleme.ui.widgets.section_panel import SectionPanel
from kurum_yedekleme.ui.widgets.status_badge import status_badge_widget


def _table_action_button(text: str, *, danger: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("TableDangerButton" if danger else "TableActionButton")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(28)
    return btn


class AreaEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        area: BackupArea | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alanı Düzenle" if area else "Yeni Alan Ekle")
        self.resize(520, 200)
        layout = QFormLayout(self)
        self._name = QLineEdit(area.name if area else "")
        self._source = QLineEdit(area.source_path if area else "")
        browse = QPushButton("Seç")
        browse.setObjectName("SecondaryButton")
        browse.clicked.connect(self._browse)
        src_row = QHBoxLayout()
        src_row.addWidget(self._source)
        src_row.addWidget(browse)
        self._enabled = QCheckBox("Aktif")
        self._enabled.setChecked(True if area is None else area.enabled)
        layout.addRow("Alan adı:", self._name)
        layout.addRow("Kaynak klasör:", src_row)
        layout.addRow(self._enabled)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Kaynak Klasör Seç")
        if path:
            self._source.setText(path)

    def values(self) -> tuple[str, str, bool]:
        return (
            self._name.text().strip(),
            self._source.text().strip(),
            self._enabled.isChecked(),
        )


class AreasPage(QWidget):
    areas_changed = Signal()

    def __init__(
        self,
        area_service: AreaService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._areas = area_service
        self._last_by_id: dict[int, BackupHistoryRecord] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "Yedekleme Alanları",
                "Birim klasörlerini tanımlayın, düzenleyin veya kaldırın.",
            )
        )

        add_btn = QPushButton("Yeni Alan Ekle")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self._add)
        layout.addWidget(add_btn)

        table_panel = SectionPanel("Tanımlı Alanlar")
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Alan adı", "Kaynak klasör", "Durum", "Son yedekleme", "Tür", "İşlem"]
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(5, 220)
        self._table.setColumnWidth(1, 360)
        table_panel.add_widget(self._table)
        layout.addWidget(table_panel, stretch=1)
        self.refresh()

    def set_last_backups(self, mapping: dict[int, BackupHistoryRecord]) -> None:
        self._last_by_id = mapping
        self.refresh()

    def refresh(self) -> None:
        areas = self._areas.list_areas()
        self._table.setRowCount(0)
        for area in areas:
            row = self._table.rowCount()
            self._table.insertRow(row)
            last = self._last_by_id.get(area.id or -1)
            last_text = "—"
            type_text = "—"
            if last is not None:
                local = last.started_at.astimezone()
                last_text = local.strftime("%d.%m.%Y %H:%M")
                type_text = last.backup_type.label_tr

            name_item = QTableWidgetItem(area.name)
            self._table.setItem(row, 0, name_item)

            path_cell = QWidget()
            path_layout = QHBoxLayout(path_cell)
            path_layout.setContentsMargins(8, 0, 8, 0)
            path_layout.addWidget(ElidedPathLabel(area.source_path))
            self._table.setCellWidget(row, 1, path_cell)

            self._table.setCellWidget(
                row,
                2,
                status_badge_widget(
                    "Aktif" if area.enabled else "Pasif",
                    "success" if area.enabled else "neutral",
                ),
            )
            self._table.setItem(row, 3, QTableWidgetItem(last_text))
            self._table.setItem(row, 4, QTableWidgetItem(type_text))

            cell = QWidget()
            row_btns = QHBoxLayout(cell)
            row_btns.setContentsMargins(6, 4, 6, 4)
            row_btns.setSpacing(6)

            edit = _table_action_button("Düzenle")
            toggle = _table_action_button(
                "Pasif yap" if area.enabled else "Aktif yap",
                danger=not area.enabled,
            )
            delete = _table_action_button("Sil", danger=True)

            area_id = area.id
            edit.clicked.connect(lambda _, i=area_id: self._edit(i))
            toggle.clicked.connect(
                lambda _, i=area_id, e=area.enabled: self._set_enabled(i, not e)
            )
            delete.clicked.connect(lambda _, i=area_id: self._delete(i))

            row_btns.addWidget(edit)
            row_btns.addWidget(toggle)
            row_btns.addWidget(delete)
            self._table.setCellWidget(row, 5, cell)
            self._table.setRowHeight(row, 42)

    def _add(self) -> None:
        dialog = AreaEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, source, enabled = dialog.values()
        try:
            self._areas.add_area(name=name, source_path=source, enabled=enabled)
        except AreaError as exc:
            QMessageBox.warning(self, "Alan", str(exc))
            return
        self.refresh()
        self.areas_changed.emit()

    def _edit(self, area_id: int | None) -> None:
        if area_id is None:
            return
        try:
            area = self._areas.get(area_id)
        except AreaError as exc:
            QMessageBox.warning(self, "Alan", str(exc))
            return
        dialog = AreaEditDialog(self, area=area)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, source, enabled = dialog.values()
        try:
            self._areas.update_area(
                area_id, name=name, source_path=source, enabled=enabled
            )
        except AreaError as exc:
            QMessageBox.warning(self, "Alan", str(exc))
            return
        self.refresh()
        self.areas_changed.emit()

    def _set_enabled(self, area_id: int | None, enabled: bool) -> None:
        if area_id is None:
            return
        try:
            self._areas.set_enabled(area_id, enabled)
        except AreaError as exc:
            QMessageBox.warning(self, "Alan", str(exc))
            return
        self.refresh()
        self.areas_changed.emit()

    def _delete(self, area_id: int | None) -> None:
        if area_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Alanı Kaldır",
            "Bu alan uygulamadan kaldırılacak. "
            "Mevcut yedekler ve geçmiş kayıtları silinmeyecektir.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._areas.delete_area(area_id)
        except AreaError as exc:
            QMessageBox.warning(self, "Alan", str(exc))
            return
        self.refresh()
        self.areas_changed.emit()
