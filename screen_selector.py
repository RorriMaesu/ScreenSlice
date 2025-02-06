import sys
import json
import logging
from PyQt5.QtCore import Qt, QRect, QTimer, QPoint
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QGuiApplication
from PyQt5.QtWidgets import QWidget, QApplication, QMessageBox

# --- Constants for Customization ---
OVERLAY_COLOR = QColor(0, 120, 215, 50)         # Semi-transparent blue fill for selection
BORDER_COLOR = QColor(0, 120, 215)                # Solid border color for selection
BORDER_WIDTH = 2
INSTRUCTION_TEXT = "Drag to select an area. Press ESC to cancel."
INSTRUCTION_COLOR = QColor(255, 255, 255, 220)    # White text (slightly transparent)
INSTRUCTION_FONT = QFont("Arial", 12)
OUTPUT_FILENAME = "selection.json"
MIN_SELECTION_SIZE = 10  # Minimum width or height in pixels for a valid selection

# Set up logging for debugging purposes.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FullScreenSelector(QWidget):
    def __init__(self):
        super().__init__()
        # We want a borderless window that stays on top.
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        # Compute the union geometry of all screens.
        self.screenGeometry = self.compute_union_geometry()
        self.setGeometry(self.screenGeometry)
        
        # Capture a screenshot of the entire area.
        # (We use QGuiApplication.primaryScreen() with parameters to capture the entire union.)
        self.screenshot = QGuiApplication.primaryScreen().grabWindow(
            0,
            self.screenGeometry.x(),
            self.screenGeometry.y(),
            self.screenGeometry.width(),
            self.screenGeometry.height()
        )

        # Variables for selection.
        self.start_point = None  # In local coordinates (relative to the window)
        self.end_point = None    # In local coordinates
        self.selection_rect = None  # In local coordinates

        # Show the window after a short delay.
        QTimer.singleShot(0, self.post_init)

    def compute_union_geometry(self):
        """Compute the union of all screen geometries (for multi-monitor setups)."""
        screens = QApplication.screens()
        if screens:
            union_rect = screens[0].geometry()
            for screen in screens[1:]:
                union_rect = union_rect.united(screen.geometry())
            logging.info("Computed union geometry: %s", union_rect)
            return union_rect
        else:
            return QApplication.primaryScreen().geometry()

    def post_init(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        logging.info("Overlay shown with geometry: %s", self.geometry())

    def global_to_local(self, global_point):
        """Convert a global point to a point local to the window."""
        # Since the window's geometry might not start at (0,0),
        # subtract the top-left of the screenGeometry.
        return global_point - self.screenGeometry.topLeft()

    def mousePressEvent(self, event):
        """Start the selection on left mouse button press."""
        if event.button() == Qt.LeftButton:
            self.start_point = self.global_to_local(event.globalPos())
            self.end_point = self.start_point
            self.selection_rect = QRect(self.start_point, self.end_point)
            self.grabMouse()
            logging.info("Mouse press at %s (local coordinates)", self.start_point)
            self.update()

    def mouseMoveEvent(self, event):
        """Update the selection rectangle while dragging."""
        if self.start_point:
            self.end_point = self.global_to_local(event.globalPos())
            self.selection_rect = QRect(self.start_point, self.end_point).normalized()
            logging.info("Mouse move: updated selection rectangle to %s", self.selection_rect)
            self.update()

    def mouseReleaseEvent(self, event):
        """Finalize the selection when the left mouse button is released."""
        if event.button() == Qt.LeftButton and self.selection_rect:
            self.end_point = self.global_to_local(event.globalPos())
            self.selection_rect = QRect(self.start_point, self.end_point).normalized()
            self.releaseMouse()
            logging.info("Mouse released: final selection rectangle is %s", self.selection_rect)

            # Validate the selection rectangle.
            if (self.selection_rect.width() < MIN_SELECTION_SIZE or
                self.selection_rect.height() < MIN_SELECTION_SIZE):
                logging.warning("Selection area too small: %s", self.selection_rect)
                self.show_message("Selection Error",
                                  "Selected area is too small. Please try again.",
                                  QMessageBox.Warning)
                self.reset_selection()
                return

            # Save the coordinates.
            if self.save_coordinates():
                self.show_message("Success",
                                  f"Selection saved to {OUTPUT_FILENAME}.",
                                  QMessageBox.Information)
                self.close()
            else:
                self.show_message("Error",
                                  "Failed to save selection. Please check your permissions and try again.",
                                  QMessageBox.Critical)
                self.reset_selection()

    def keyPressEvent(self, event):
        """Cancel the selection if the ESC key is pressed."""
        if event.key() == Qt.Key_Escape:
            logging.info("Selection cancelled by user.")
            self.show_message("Cancelled", "Selection was cancelled.", QMessageBox.Information)
            self.close()

    def paintEvent(self, event):
        """Draw the screenshot background, dark overlay, selection rectangle, and instructions."""
        painter = QPainter(self)
        # Draw the screenshot (positioned at (0,0) because the widget's coordinate system is local).
        painter.drawPixmap(0, 0, self.screenshot)
        # Draw a semi-transparent dark overlay over the screenshot.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        # Draw the selection rectangle if it exists.
        if self.selection_rect:
            painter.fillRect(self.selection_rect, OVERLAY_COLOR)
            pen = QPen(BORDER_COLOR, BORDER_WIDTH)
            painter.setPen(pen)
            painter.drawRect(self.selection_rect)
        # Draw instructional text at the top-center.
        painter.setFont(INSTRUCTION_FONT)
        painter.setPen(INSTRUCTION_COLOR)
        text_rect = painter.fontMetrics().boundingRect(INSTRUCTION_TEXT)
        text_x = (self.width() - text_rect.width()) // 2
        text_y = 20 + text_rect.height()
        painter.drawText(text_x, text_y, INSTRUCTION_TEXT)

    def save_coordinates(self):
        """Save the selection rectangle's global coordinates to a JSON file."""
        if self.selection_rect:
            # Convert the local selection rectangle to global coordinates by adding back the offset.
            global_top_left = self.screenGeometry.topLeft() + self.selection_rect.topLeft()
            abs_rect = QRect(global_top_left, self.selection_rect.size())
            coords = {
                "x": abs_rect.x(),
                "y": abs_rect.y(),
                "width": abs_rect.width(),
                "height": abs_rect.height()
            }
            try:
                with open(OUTPUT_FILENAME, "w") as json_file:
                    json.dump(coords, json_file, indent=4)
                logging.info("Selection saved: %s", coords)
                return True
            except Exception as e:
                logging.error("Error saving selection: %s", e)
                return False
        return False

    def reset_selection(self):
        """Reset the selection state to allow a new selection attempt."""
        logging.info("Resetting selection.")
        self.start_point = None
        self.end_point = None
        self.selection_rect = None
        self.update()

    def show_message(self, title, message, icon):
        """Display a message box for user feedback."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    selector = FullScreenSelector()
    sys.exit(app.exec_())
