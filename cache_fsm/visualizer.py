from __future__ import annotations

import math
import sys
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .components import CacheControllerFSM, CacheSystemSimulator, SimpleCPU, SimpleMemory
from .models import CPURequest, CPUResponse, ControllerState, CycleTrace
from .scenarios import Scenario, default_scenarios


def _fmt_addr(value: int | None) -> str:
    if value is None:
        return "-"
    return f"0x{value:X}"


def _fmt_request(req: CPURequest | None) -> str:
    if req is None:
        return "-"
    if req.write_data is not None:
        return f"#{req.req_id} {req.req_type.value} {_fmt_addr(req.address)} <= {req.write_data}"
    return f"#{req.req_id} {req.req_type.value} {_fmt_addr(req.address)}"


def _fmt_response(resp: CPUResponse | None) -> str:
    if resp is None:
        return "-"
    return (
        f"#{resp.req_id} {resp.req_type.value} {_fmt_addr(resp.address)} "
        f"hit={resp.hit} data={resp.data} wait={resp.wait_cycles}"
    )


def create_simulator(scenario: Scenario) -> CacheSystemSimulator:
    cpu = SimpleCPU(list(scenario.requests))
    memory = SimpleMemory(
        initial_storage=dict(scenario.initial_memory),
        read_latency=scenario.read_latency,
        write_latency=scenario.write_latency,
    )
    controller = CacheControllerFSM()
    return CacheSystemSimulator(cpu=cpu, memory=memory, controller=controller)


class FSMCanvas(QWidget):
    """Custom-painted FSM diagram with highlighted transitions and states."""

    EDGE_COLOR = QColor("#4E5D6C")
    EDGE_ACTIVE = QColor("#E85D04")
    NODE_BORDER = QColor("#1E2A38")
    NODE_TEXT = QColor("#12263A")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.active_state = ControllerState.IDLE
        self.active_transition = "NONE"
        self.setMinimumSize(780, 680)

    def set_active(self, state: ControllerState, transition_key: str) -> None:
        self.active_state = state
        self.active_transition = transition_key
        self.update()

    def _layout(self) -> tuple[dict[ControllerState, QPointF], float]:
        rect = self.rect()
        w = max(1.0, float(rect.width()))
        h = max(1.0, float(rect.height()))

        radius = max(70.0, min(96.0, min(w, h) * 0.115))
        centers = {
            ControllerState.IDLE: QPointF(w * 0.19, h * 0.17),
            ControllerState.COMPARE_TAG: QPointF(w * 0.78, h * 0.17),
            ControllerState.ALLOCATE: QPointF(w * 0.24, h * 0.73),
            ControllerState.WRITE_BACK: QPointF(w * 0.78, h * 0.73),
        }
        return centers, radius

    @staticmethod
    def _edge_point(src: QPointF, dst: QPointF, radius: float, extra: float = 0.0) -> QPointF:
        dx = dst.x() - src.x()
        dy = dst.y() - src.y()
        mag = math.hypot(dx, dy)
        if mag <= 0.001:
            return QPointF(src)
        scale = (radius + extra) / mag
        return QPointF(src.x() + dx * scale, src.y() + dy * scale)

    def _draw_background(self, painter: QPainter) -> None:
        rect = self.rect()
        gradient = QLinearGradient(0, 0, 0, float(rect.height()))
        gradient.setColorAt(0.0, QColor("#E9F2FB"))
        gradient.setColorAt(1.0, QColor("#DCEAF8"))
        painter.fillRect(rect, gradient)

        painter.setPen(QPen(QColor(255, 255, 255, 85), 1))
        for x in range(20, rect.width(), 30):
            painter.drawLine(x, 0, x, rect.height())

    def _build_transitions(
        self,
        centers: dict[ControllerState, QPointF],
        radius: float,
    ) -> dict[str, tuple[QPainterPath, QPointF, str]]:
        idle = centers[ControllerState.IDLE]
        compare = centers[ControllerState.COMPARE_TAG]
        allocate = centers[ControllerState.ALLOCATE]
        write_back = centers[ControllerState.WRITE_BACK]

        transitions: dict[str, tuple[QPainterPath, QPointF, str]] = {}

        path = QPainterPath(QPointF(idle.x() + radius * 0.98, idle.y() + 20))
        path.lineTo(compare.x() - radius * 0.98, compare.y() + 20)
        transitions["IDLE_TO_COMPARE"] = (
            path,
            QPointF((idle.x() + compare.x()) * 0.5, idle.y() + 44),
            "Valid CPU request",
        )

        path = QPainterPath(QPointF(compare.x() - radius * 0.98, compare.y() - 28))
        path.lineTo(idle.x() + radius * 0.98, idle.y() - 28)
        transitions["COMPARE_TO_IDLE_HIT"] = (
            path,
            QPointF((idle.x() + compare.x()) * 0.5, idle.y() - 52),
            "Cache hit / mark cache ready",
        )

        miss_clean_start = self._edge_point(compare, allocate, radius, extra=4)
        miss_clean_end = self._edge_point(allocate, compare, radius, extra=2)
        path = QPainterPath(miss_clean_start)
        path.cubicTo(
            QPointF(miss_clean_start.x() - 90, miss_clean_start.y() + 62),
            QPointF(miss_clean_end.x() + 84, miss_clean_end.y() - 72),
            miss_clean_end,
        )
        transitions["COMPARE_TO_ALLOCATE_MISS_CLEAN"] = (
            path,
            QPointF((compare.x() + allocate.x()) * 0.5 + 24, (compare.y() + allocate.y()) * 0.5),
            "Cache miss and\nold block is clean",
        )

        alloc_ready_start = self._edge_point(allocate, compare, radius, extra=4)
        alloc_ready_end = self._edge_point(compare, allocate, radius, extra=2)
        path = QPainterPath(alloc_ready_start)
        path.cubicTo(
            QPointF(alloc_ready_start.x() + 92, alloc_ready_start.y() - 74),
            QPointF(alloc_ready_end.x() - 94, alloc_ready_end.y() + 58),
            alloc_ready_end,
        )
        transitions["ALLOCATE_TO_COMPARE_READY"] = (
            path,
            QPointF((compare.x() + allocate.x()) * 0.5 - 58, (compare.y() + allocate.y()) * 0.5 - 4),
            "Memory ready",
        )

        path = QPainterPath(QPointF(compare.x(), compare.y() + radius * 0.98))
        path.lineTo(write_back.x(), write_back.y() - radius * 0.98)
        transitions["COMPARE_TO_WRITEBACK_MISS_DIRTY"] = (
            path,
            QPointF(compare.x() + 90, (compare.y() + write_back.y()) * 0.5),
            "Cache miss and\nold block is dirty",
        )

        path = QPainterPath(QPointF(write_back.x() - radius * 0.98, write_back.y()))
        path.lineTo(allocate.x() + radius * 0.98, allocate.y())
        transitions["WRITEBACK_TO_ALLOCATE_READY"] = (
            path,
            QPointF((write_back.x() + allocate.x()) * 0.5, write_back.y() - 26),
            "Memory ready",
        )

        loop_start = QPointF(allocate.x() + radius * 0.40, allocate.y() + radius * 0.70)
        path = QPainterPath(loop_start)
        path.cubicTo(
            QPointF(allocate.x() + radius * 1.30, allocate.y() + radius * 1.15),
            QPointF(allocate.x() - radius * 0.20, allocate.y() + radius * 1.58),
            QPointF(allocate.x() - radius * 0.03, allocate.y() + radius * 0.46),
        )
        transitions["ALLOCATE_STALL"] = (
            path,
            QPointF(allocate.x() + radius * 1.23, allocate.y() + radius * 1.01),
            "Memory not ready",
        )

        loop_start = QPointF(write_back.x() + radius * 0.40, write_back.y() + radius * 0.70)
        path = QPainterPath(loop_start)
        path.cubicTo(
            QPointF(write_back.x() + radius * 1.30, write_back.y() + radius * 1.15),
            QPointF(write_back.x() - radius * 0.20, write_back.y() + radius * 1.58),
            QPointF(write_back.x() - radius * 0.03, write_back.y() + radius * 0.46),
        )
        transitions["WRITEBACK_STALL"] = (
            path,
            QPointF(write_back.x() + radius * 1.23, write_back.y() + radius * 1.01),
            "Memory not ready",
        )

        return transitions

    @staticmethod
    def _draw_arrowhead(painter: QPainter, path: QPainterPath, color: QColor) -> None:
        tip = path.pointAtPercent(1.0)
        prev = path.pointAtPercent(0.985)
        dx = tip.x() - prev.x()
        dy = tip.y() - prev.y()
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return

        angle = math.atan2(dy, dx)
        arrow_size = 12.0
        left = QPointF(
            tip.x() - arrow_size * math.cos(angle - math.pi / 6),
            tip.y() - arrow_size * math.sin(angle - math.pi / 6),
        )
        right = QPointF(
            tip.x() - arrow_size * math.cos(angle + math.pi / 6),
            tip.y() - arrow_size * math.sin(angle + math.pi / 6),
        )

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([tip, left, right]))

    @staticmethod
    def _draw_label(painter: QPainter, label: str, center: QPointF, active: bool) -> None:
        font = QFont("Noto Sans", 10)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        lines = label.split("\n")
        max_width = max(fm.horizontalAdvance(line) for line in lines)
        total_height = fm.height() * len(lines)

        box = QRectF(
            center.x() - max_width / 2 - 8,
            center.y() - total_height / 2 - 6,
            max_width + 16,
            total_height + 12,
        )

        bg = QColor(255, 255, 255, 230 if active else 205)
        border = QColor("#F08C00") if active else QColor(60, 90, 120, 110)
        painter.setPen(QPen(border, 1.5 if active else 1.0))
        painter.setBrush(bg)
        painter.drawRoundedRect(box, 8, 8)

        painter.setPen(QColor("#8A3D00") if active else QColor("#27364A"))
        baseline = box.top() + 6 + fm.ascent()
        for line in lines:
            x = center.x() - fm.horizontalAdvance(line) / 2
            painter.drawText(QPointF(x, baseline), line)
            baseline += fm.height()

    def _draw_transition(
        self,
        painter: QPainter,
        path: QPainterPath,
        label: str,
        label_pos: QPointF,
        active: bool,
    ) -> None:
        base_color = self.EDGE_ACTIVE if active else self.EDGE_COLOR

        if active:
            glow = QColor(base_color)
            glow.setAlpha(80)
            painter.setPen(QPen(glow, 9.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        painter.setPen(
            QPen(
                base_color,
                3.6 if active else 2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        self._draw_arrowhead(painter, path, base_color)
        self._draw_label(painter, label, label_pos, active)

    def _draw_state(
        self,
        painter: QPainter,
        center: QPointF,
        radius: float,
        title: str,
        subtitle: str,
        active: bool,
    ) -> None:
        shadow = QRectF(
            center.x() - radius + 10,
            center.y() - radius + 10,
            radius * 2,
            radius * 2,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawEllipse(shadow)

        body = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        gradient = QLinearGradient(body.topLeft(), body.bottomRight())
        if active:
            gradient.setColorAt(0.0, QColor("#FFE8B6"))
            gradient.setColorAt(1.0, QColor("#FFBD73"))
            outline = QColor("#B84700")
            text_color = QColor("#7A2500")
        else:
            gradient.setColorAt(0.0, QColor("#FFFFFF"))
            gradient.setColorAt(1.0, QColor("#DDE9F5"))
            outline = self.NODE_BORDER
            text_color = self.NODE_TEXT

        painter.setBrush(gradient)
        painter.setPen(QPen(outline, 3.8 if active else 2.2))
        painter.drawEllipse(body)

        title_font = QFont("Noto Sans", 15, QFont.Weight.Bold)
        subtitle_font = QFont("Noto Sans", 11)

        painter.setPen(text_color)
        painter.setFont(title_font)
        title_rect = QRectF(body.left() + 8, center.y() - 34, body.width() - 16, 28)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)

        if subtitle:
            painter.setFont(subtitle_font)
            subtitle_rect = QRectF(body.left() + 14, center.y() - 2, body.width() - 28, 52)
            painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, subtitle)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        self._draw_background(painter)
        centers, radius = self._layout()
        transitions = self._build_transitions(centers, radius)

        for key, (path, label_pos, label) in transitions.items():
            self._draw_transition(
                painter,
                path,
                label,
                label_pos,
                active=(key == self.active_transition),
            )

        self._draw_state(
            painter,
            centers[ControllerState.IDLE],
            radius,
            "Idle",
            "",
            active=(self.active_state is ControllerState.IDLE),
        )
        self._draw_state(
            painter,
            centers[ControllerState.COMPARE_TAG],
            radius,
            "Compare Tag",
            "If valid and hit: set ready\nIf write hit: set dirty",
            active=(self.active_state is ControllerState.COMPARE_TAG),
        )
        self._draw_state(
            painter,
            centers[ControllerState.ALLOCATE],
            radius,
            "Allocate",
            "Read new block\nfrom memory",
            active=(self.active_state is ControllerState.ALLOCATE),
        )
        self._draw_state(
            painter,
            centers[ControllerState.WRITE_BACK],
            radius,
            "Write-Back",
            "Write old block\nto memory",
            active=(self.active_state is ControllerState.WRITE_BACK),
        )


class FSMVisualizerApp:
    def __init__(self) -> None:
        self.qt_app = QApplication.instance()
        if self.qt_app is None:
            self.qt_app = QApplication(sys.argv)

        self.scenarios = default_scenarios()
        self.selected_scenario = "all_paths"
        self.simulator = create_simulator(self.scenarios[self.selected_scenario])

        self._running = False
        self._timer = QTimer()
        self._timer.timeout.connect(self._auto_step)

        self.signal_labels: dict[str, QLabel] = {}
        self._build_ui()
        self._refresh_panels(None)

    def _build_ui(self) -> None:
        self.window = QWidget()
        self.window.setWindowTitle("Cache Controller FSM Simulator (PyQt6)")
        self.window.resize(1380, 920)
        self.window.setStyleSheet(self._stylesheet())

        root = QVBoxLayout(self.window)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        control_bar = QFrame()
        control_bar.setObjectName("ControlBar")
        controls = QHBoxLayout(control_bar)
        controls.setContentsMargins(12, 10, 12, 10)
        controls.setSpacing(10)

        controls.addWidget(QLabel("Scenario:"))
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems(list(self.scenarios.keys()))
        self.scenario_combo.setCurrentText(self.selected_scenario)
        self.scenario_combo.currentTextChanged.connect(self._on_scenario_change)
        self.scenario_combo.setMinimumWidth(190)
        controls.addWidget(self.scenario_combo)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_simulation)
        controls.addWidget(self.reset_button)

        self.step_button = QPushButton("Step")
        self.step_button.clicked.connect(self.step_once)
        controls.addWidget(self.step_button)

        self.run_button = QPushButton("Auto Run")
        self.run_button.clicked.connect(self.toggle_run)
        controls.addWidget(self.run_button)

        self.run_end_button = QPushButton("Run To End")
        self.run_end_button.clicked.connect(self.run_to_end)
        controls.addWidget(self.run_end_button)

        controls.addSpacing(8)
        controls.addWidget(QLabel("Speed (ms):"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(80)
        self.speed_slider.setMaximum(1200)
        self.speed_slider.setValue(450)
        self.speed_slider.setFixedWidth(220)
        self.speed_slider.valueChanged.connect(self._on_speed_change)
        controls.addWidget(self.speed_slider)

        self.speed_value = QLabel(str(self.speed_slider.value()))
        self.speed_value.setMinimumWidth(40)
        controls.addWidget(self.speed_value)

        self.scenario_desc = QLabel()
        self.scenario_desc.setObjectName("ScenarioDesc")
        self.scenario_desc.setWordWrap(True)
        controls.addWidget(self.scenario_desc, stretch=1)

        root.addWidget(control_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QFrame()
        left.setObjectName("CanvasCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        self.canvas = FSMCanvas()
        left_layout.addWidget(self.canvas, stretch=1)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("SidePanel")
        right.setMinimumWidth(410)
        right.setMaximumWidth(520)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)

        status_group = QGroupBox("Current Step")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(4)
        self.cycle_label = QLabel("Cycle: 0")
        self.state_label = QLabel("State: Idle")
        self.transition_label = QLabel("Transition: -")
        self.request_label = QLabel("Issued Request: -")
        self.response_label = QLabel("Completed Response: -")
        for item in [
            self.cycle_label,
            self.state_label,
            self.transition_label,
            self.request_label,
            self.response_label,
        ]:
            status_layout.addWidget(item)
        right_layout.addWidget(status_group)

        signal_group = QGroupBox("Interface Signals")
        signal_grid = QGridLayout(signal_group)
        signal_grid.setHorizontalSpacing(10)
        signal_grid.setVerticalSpacing(4)

        signal_keys = [
            "cpu_req_valid",
            "cpu_waiting",
            "cache_ready",
            "cache_hit",
            "mem_read",
            "mem_write",
            "mem_ready",
            "mem_busy",
            "mem_addr",
        ]
        for row, key in enumerate(signal_keys):
            name = QLabel(f"{key}:")
            name.setObjectName("SignalName")
            value = QLabel("-")
            value.setObjectName("SignalValue")
            signal_grid.addWidget(name, row, 0)
            signal_grid.addWidget(value, row, 1)
            self.signal_labels[key] = value
        right_layout.addWidget(signal_group)

        cache_group = QGroupBox("Cache Line")
        cache_layout = QVBoxLayout(cache_group)
        self.cache_line_label = QLabel("valid=False dirty=False tag=- data=0")
        cache_layout.addWidget(self.cache_line_label)
        right_layout.addWidget(cache_group)

        queue_group = QGroupBox("CPU Queue")
        queue_layout = QVBoxLayout(queue_group)
        self.queue_label = QLabel("pending=0 active=-")
        queue_layout.addWidget(self.queue_label)
        right_layout.addWidget(queue_group)

        trace_group = QGroupBox("Cycle Trace")
        trace_layout = QVBoxLayout(trace_group)
        self.trace_text = QTextEdit()
        self.trace_text.setReadOnly(True)
        mono = QFont("DejaVu Sans Mono", 10)
        self.trace_text.setFont(mono)
        trace_layout.addWidget(self.trace_text)
        right_layout.addWidget(trace_group, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([930, 430])

        root.addWidget(splitter, stretch=1)

    @staticmethod
    def _stylesheet() -> str:
        return """
        QWidget {
            color: #18334a;
            background: #ecf3fa;
            font-family: 'Noto Sans';
            font-size: 13px;
        }
        QFrame#ControlBar {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #fef8f2, stop:1 #f2f8ff);
            border: 1px solid #b8cde1;
            border-radius: 12px;
        }
        QFrame#CanvasCard, QFrame#SidePanel {
            background: #f7fbff;
            border: 1px solid #bfd4e7;
            border-radius: 12px;
        }
        QGroupBox {
            border: 1px solid #c7d9ea;
            border-radius: 10px;
            margin-top: 8px;
            padding-top: 8px;
            font-weight: 600;
            background: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: #114b77;
        }
        QPushButton {
            background: #2c7fb8;
            color: #ffffff;
            border: 1px solid #1f628f;
            border-radius: 8px;
            padding: 5px 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #236f9f;
        }
        QPushButton:pressed {
            background: #185a84;
        }
        QComboBox, QTextEdit {
            background: #ffffff;
            border: 1px solid #b6cadc;
            border-radius: 8px;
            padding: 4px;
        }
        QLabel#ScenarioDesc {
            color: #3a5368;
            font-style: italic;
        }
        QLabel#SignalName {
            color: #1c4966;
            font-weight: 600;
        }
        QLabel#SignalValue {
            color: #14324a;
        }
        """

    def _on_scenario_change(self, key: str) -> None:
        self.selected_scenario = key
        self.reset_simulation()

    def _on_speed_change(self, value: int) -> None:
        self.speed_value.setText(str(value))
        if self._running:
            self._timer.setInterval(value)

    def _append_trace(self, line: str) -> None:
        self.trace_text.append(line)
        cursor = self.trace_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.trace_text.setTextCursor(cursor)

    def _refresh_panels(self, trace: Optional[CycleTrace]) -> None:
        scenario = self.scenarios[self.selected_scenario]
        self.scenario_desc.setText(scenario.description)

        if trace is None:
            self.canvas.set_active(self.simulator.controller.state, "NONE")
            self.cycle_label.setText(f"Cycle: {self.simulator.cycle}")
            self.state_label.setText(f"State: {self.simulator.controller.state.value}")
            self.transition_label.setText("Transition: -")
            self.request_label.setText("Issued Request: -")
            self.response_label.setText("Completed Response: -")
            for label in self.signal_labels.values():
                label.setText("-")
        else:
            self.canvas.set_active(trace.state_after, trace.transition_key)
            self.cycle_label.setText(f"Cycle: {trace.cycle}")
            self.state_label.setText(f"State: {trace.state_before.value} -> {trace.state_after.value}")
            self.transition_label.setText(f"Transition: {trace.transition_label}")
            self.request_label.setText(f"Issued Request: {_fmt_request(trace.issued_request)}")
            self.response_label.setText(f"Completed Response: {_fmt_response(trace.completed_response)}")

            self.signal_labels["cpu_req_valid"].setText(str(trace.signals.cpu_req_valid))
            self.signal_labels["cpu_waiting"].setText(str(trace.signals.cpu_waiting))
            self.signal_labels["cache_ready"].setText(str(trace.signals.cache_ready))
            self.signal_labels["cache_hit"].setText(str(trace.signals.cache_hit))
            self.signal_labels["mem_read"].setText(str(trace.signals.mem_read))
            self.signal_labels["mem_write"].setText(str(trace.signals.mem_write))
            self.signal_labels["mem_ready"].setText(str(trace.signals.mem_ready))
            self.signal_labels["mem_busy"].setText(str(trace.signals.mem_busy))
            self.signal_labels["mem_addr"].setText(_fmt_addr(trace.signals.mem_addr))

            line = (
                f"C{trace.cycle:03d} | {trace.state_before.value} -> {trace.state_after.value} | "
                f"{trace.transition_label} | req={_fmt_request(trace.issued_request)} | "
                f"resp={_fmt_response(trace.completed_response)}"
            )
            self._append_trace(line)

        line = self.simulator.controller.cache_line
        self.cache_line_label.setText(
            f"valid={line.valid} dirty={line.dirty} tag={_fmt_addr(line.tag)} data={line.data}"
        )
        self.queue_label.setText(
            f"pending={self.simulator.cpu.queue_depth} active={_fmt_request(self.simulator.cpu.current_request)}"
        )

    def reset_simulation(self) -> None:
        self.stop_run()
        scenario = self.scenarios[self.selected_scenario]
        self.simulator = create_simulator(scenario)
        self.trace_text.clear()
        self._refresh_panels(None)

    def step_once(self) -> None:
        if self.simulator.is_done():
            self.stop_run()
            return

        trace = self.simulator.step()
        self._refresh_panels(trace)

        if self.simulator.is_done():
            self._append_trace("Simulation complete.")
            self.stop_run()

    def _auto_step(self) -> None:
        if not self._running:
            return
        if self.simulator.is_done():
            self.stop_run()
            return
        self.step_once()

    def toggle_run(self) -> None:
        if self._running:
            self.stop_run()
        else:
            self.start_run()

    def start_run(self) -> None:
        self._running = True
        self.run_button.setText("Pause")
        self._timer.start(self.speed_slider.value())

    def stop_run(self) -> None:
        self._running = False
        self.run_button.setText("Auto Run")
        self._timer.stop()

    def run_to_end(self) -> None:
        self.stop_run()
        guard = 0
        while not self.simulator.is_done() and guard < 450:
            self.step_once()
            QApplication.processEvents()
            guard += 1

    def run(self) -> None:
        self.window.show()
        self.qt_app.exec()
