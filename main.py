import sys
import re
import os
import json
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTableWidget, QTableWidgetItem, QTextEdit, QSplitter,
                             QHeaderView, QMessageBox, QProgressDialog, QComboBox,
                             QLineEdit, QGroupBox, QFormLayout, QSpinBox, QDialog,
                             QGraphicsView, QGraphicsScene, QGraphicsLineItem,
                             QGraphicsRectItem, QSlider, QScrollArea, QFrame,
                             QRadioButton, QButtonGroup, QTabWidget, QListWidget,
                             QListWidgetItem, QAbstractItemView, QCheckBox, QMenu)
from PyQt5.QtCore import Qt, QRectF, QPointF, QLineF
from PyQt5.QtGui import QFont, QPixmap, QImage, QPen, QColor, QBrush, QPainter, QIcon
import fitz  # PyMuPDF para leer PDFs
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import DictionaryObject, NameObject, ArrayObject, NumberObject, createStringObject


def get_app_path():
    """Obtiene la ruta de la aplicación (funciona como script y como .exe)"""
    if getattr(sys, 'frozen', False):
        # Ejecutando como .exe (PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # Ejecutando como script de Python
        return os.path.dirname(os.path.abspath(__file__))


class GridEditorDialog(QDialog):
    """
    Editor visual para definir manualmente la cuadrícula del esquema.
    Permite al usuario cargar un PDF y dibujar las líneas de columnas y filas
    arrastrando sobre la imagen.
    
    Los cambios se guardan automáticamente en un archivo JSON asociado al PDF.
    """
    
    def __init__(self, parent=None, pdf_path=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.page_num = 0
        self.zoom_factor = 1.0
        self.column_lines = []  # Lista de posiciones X de líneas verticales
        self.row_lines = []     # Lista de posiciones Y de líneas horizontales
        self.current_mode = 'column'  # 'column' o 'row'
        self.pdf_doc = None
        self.page_width = 0
        self.page_height = 0
        self.config_file = None  # Ruta del archivo de configuración
        self.init_ui()
        
        if pdf_path:
            self.load_pdf(pdf_path)
            self.load_saved_config()  # Cargar configuración guardada
    
    def init_ui(self):
        self.setWindowTitle('Editor Visual de Cuadrícula')
        self.setGeometry(100, 100, 1200, 800)
        self.setModal(True)
        
        main_layout = QVBoxLayout(self)
        
        # Barra de herramientas
        toolbar = QHBoxLayout()
        
        # Botón cargar PDF
        self.load_btn = QPushButton('📂 Cargar PDF')
        self.load_btn.clicked.connect(self.on_load_pdf)
        toolbar.addWidget(self.load_btn)
        
        # Selector de página
        toolbar.addWidget(QLabel('Página:'))
        self.page_spinbox = QSpinBox()
        self.page_spinbox.setRange(1, 1)
        self.page_spinbox.setValue(1)
        self.page_spinbox.valueChanged.connect(self.on_page_changed)
        toolbar.addWidget(self.page_spinbox)
        
        toolbar.addSpacing(20)
        
        # Selector de modo
        toolbar.addWidget(QLabel('Dibujar:'))
        self.mode_group = QButtonGroup(self)
        
        self.col_radio = QRadioButton('Columnas (verticales)')
        self.col_radio.setChecked(True)
        self.col_radio.toggled.connect(lambda: self.set_mode('column'))
        self.mode_group.addButton(self.col_radio)
        toolbar.addWidget(self.col_radio)
        
        self.row_radio = QRadioButton('Filas (horizontales)')
        self.row_radio.toggled.connect(lambda: self.set_mode('row'))
        self.mode_group.addButton(self.row_radio)
        toolbar.addWidget(self.row_radio)
        
        toolbar.addSpacing(20)
        
        # Zoom
        toolbar.addWidget(QLabel('Zoom:'))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(25, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setMaximumWidth(150)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        toolbar.addWidget(self.zoom_slider)
        self.zoom_label = QLabel('100%')
        toolbar.addWidget(self.zoom_label)
        
        toolbar.addStretch()
        
        # Botones de acción
        self.clear_cols_btn = QPushButton('🗑️ Borrar Columnas')
        self.clear_cols_btn.clicked.connect(self.clear_columns)
        toolbar.addWidget(self.clear_cols_btn)
        
        self.clear_rows_btn = QPushButton('🗑️ Borrar Filas')
        self.clear_rows_btn.clicked.connect(self.clear_rows)
        toolbar.addWidget(self.clear_rows_btn)
        
        main_layout.addLayout(toolbar)
        
        # Área de visualización del PDF
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.setMouseTracking(True)
        self.view.viewport().installEventFilter(self)
        main_layout.addWidget(self.view)
        
        # Info panel
        info_layout = QHBoxLayout()
        self.info_label = QLabel('Haz clic en la imagen para añadir líneas. Clic derecho para eliminar la última.')
        self.info_label.setStyleSheet('color: #666; font-style: italic;')
        info_layout.addWidget(self.info_label)
        
        info_layout.addStretch()
        
        self.cols_count_label = QLabel('Columnas: 0')
        self.cols_count_label.setStyleSheet('font-weight: bold; color: blue;')
        info_layout.addWidget(self.cols_count_label)
        
        info_layout.addSpacing(20)
        
        self.rows_count_label = QLabel('Filas: 0')
        self.rows_count_label.setStyleSheet('font-weight: bold; color: green;')
        info_layout.addWidget(self.rows_count_label)
        
        main_layout.addLayout(info_layout)
        
        # Botones de diálogo
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.cancel_btn = QPushButton('Cancelar')
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton('✅ Guardar y Aplicar')
        self.save_btn.clicked.connect(self.accept)
        self.save_btn.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        ''')
        buttons_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(buttons_layout)
        
        # Línea de preview
        self.preview_line = None
    
    def eventFilter(self, obj, event):
        """Captura eventos del mouse en el viewport"""
        from PyQt5.QtCore import QEvent
        
        if obj == self.view.viewport():
            if event.type() == QEvent.MouseButtonPress:
                self.on_mouse_press(event)
                return True
            elif event.type() == QEvent.MouseMove:
                self.on_mouse_move(event)
                return True
        
        return super().eventFilter(obj, event)
    
    def on_mouse_press(self, event):
        """Maneja el clic del mouse"""
        if not self.pdf_doc:
            return
        
        # Convertir posición del viewport a posición de la escena
        scene_pos = self.view.mapToScene(event.pos())
        x = scene_pos.x() / self.zoom_factor
        y = scene_pos.y() / self.zoom_factor
        
        # Verificar que está dentro de los límites
        if x < 0 or x > self.page_width or y < 0 or y > self.page_height:
            return
        
        if event.button() == Qt.LeftButton:
            # Añadir línea
            if self.current_mode == 'column':
                self.column_lines.append(x)
                self.column_lines.sort()
            else:
                self.row_lines.append(y)
                self.row_lines.sort()
            self.update_lines()
            
        elif event.button() == Qt.RightButton:
            # Eliminar última línea del modo actual
            if self.current_mode == 'column' and self.column_lines:
                # Eliminar la más cercana
                closest = min(self.column_lines, key=lambda lx: abs(lx - x))
                self.column_lines.remove(closest)
            elif self.current_mode == 'row' and self.row_lines:
                closest = min(self.row_lines, key=lambda ly: abs(ly - y))
                self.row_lines.remove(closest)
            self.update_lines()
    
    def on_mouse_move(self, event):
        """Muestra preview de la línea al mover el mouse"""
        if not self.pdf_doc:
            return
        
        scene_pos = self.view.mapToScene(event.pos())
        x = scene_pos.x()
        y = scene_pos.y()
        
        # Eliminar preview anterior
        if self.preview_line:
            self.scene.removeItem(self.preview_line)
            self.preview_line = None
        
        # Crear nueva línea de preview
        pen = QPen(QColor(255, 0, 0, 100), 2, Qt.DashLine)
        
        if self.current_mode == 'column':
            self.preview_line = self.scene.addLine(
                x, 0, x, self.page_height * self.zoom_factor, pen
            )
        else:
            self.preview_line = self.scene.addLine(
                0, y, self.page_width * self.zoom_factor, y, pen
            )
    
    def on_load_pdf(self):
        """Carga un archivo PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Seleccionar PDF', '', 'Archivos PDF (*.pdf)'
        )
        if file_path:
            self.load_pdf(file_path)
    
    def load_pdf(self, path):
        """Carga el PDF y muestra la primera página"""
        try:
            if self.pdf_doc:
                self.pdf_doc.close()
            
            self.pdf_path = path
            self.pdf_doc = fitz.open(path)
            self.page_spinbox.setMaximum(len(self.pdf_doc))
            self.page_spinbox.setValue(1)
            self.render_page()
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Error al cargar el PDF:\n{str(e)}')
    
    def on_page_changed(self, value):
        """Cambia la página mostrada"""
        self.page_num = value - 1
        self.render_page()
    
    def on_zoom_changed(self, value):
        """Cambia el nivel de zoom"""
        self.zoom_factor = value / 100.0
        self.zoom_label.setText(f'{value}%')
        self.render_page()
    
    def set_mode(self, mode):
        """Cambia el modo de dibujo"""
        self.current_mode = mode
        if mode == 'column':
            self.info_label.setText('Modo COLUMNAS: Clic para añadir línea vertical. Clic derecho para eliminar.')
        else:
            self.info_label.setText('Modo FILAS: Clic para añadir línea horizontal. Clic derecho para eliminar.')
    
    def render_page(self):
        """Renderiza la página actual del PDF"""
        if not self.pdf_doc:
            return
        
        page = self.pdf_doc[self.page_num]
        self.page_width = page.rect.width
        self.page_height = page.rect.height
        
        # Renderizar a imagen
        mat = fitz.Matrix(self.zoom_factor * 2, self.zoom_factor * 2)  # Mayor resolución
        pix = page.get_pixmap(matrix=mat)
        
        # Convertir a QImage
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        
        # Escalar al zoom deseado
        scaled_pixmap = pixmap.scaled(
            int(self.page_width * self.zoom_factor),
            int(self.page_height * self.zoom_factor),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Limpiar escena y añadir imagen
        self.scene.clear()
        self.preview_line = None
        self.scene.addPixmap(scaled_pixmap)
        self.scene.setSceneRect(0, 0, scaled_pixmap.width(), scaled_pixmap.height())
        
        # Redibujar líneas
        self.update_lines()
    
    def update_lines(self):
        """Actualiza las líneas dibujadas en la escena y guarda automáticamente"""
        # Eliminar líneas anteriores (pero no la imagen)
        for item in self.scene.items():
            if isinstance(item, QGraphicsLineItem):
                self.scene.removeItem(item)
        
        # Dibujar líneas de columnas (azules)
        pen_col = QPen(QColor(0, 0, 255), 2)
        for x in self.column_lines:
            scaled_x = x * self.zoom_factor
            self.scene.addLine(
                scaled_x, 0, 
                scaled_x, self.page_height * self.zoom_factor, 
                pen_col
            )
        
        # Dibujar líneas de filas (verdes)
        pen_row = QPen(QColor(0, 128, 0), 2)
        for y in self.row_lines:
            scaled_y = y * self.zoom_factor
            self.scene.addLine(
                0, scaled_y, 
                self.page_width * self.zoom_factor, scaled_y, 
                pen_row
            )
        
        # Actualizar contadores
        self.cols_count_label.setText(f'Columnas: {len(self.column_lines)}')
        self.rows_count_label.setText(f'Filas: {len(self.row_lines)}')
        
        # Guardar automáticamente
        self.save_config()
    
    def clear_columns(self):
        """Elimina todas las líneas de columnas"""
        self.column_lines.clear()
        self.update_lines()
    
    def clear_rows(self):
        """Elimina todas las líneas de filas"""
        self.row_lines.clear()
        self.update_lines()
    
    def get_grid_data(self):
        """Devuelve los datos de la cuadrícula configurada"""
        return {
            'column_positions': sorted(self.column_lines),
            'row_positions': sorted(self.row_lines),
            'page_width': self.page_width,
            'page_height': self.page_height
        }
    
    def get_config_file_path(self):
        """Obtiene la ruta del archivo de configuración genérico"""
        # Guardar en la carpeta del usuario o junto al script
        # Configuración genérica para todos los PDFs
        app_dir = get_app_path()
        return os.path.join(app_dir, 'grid_config.json')
    
    def save_config(self):
        """Guarda la configuración genérica de la cuadrícula automáticamente"""
        config_path = self.get_config_file_path()
        
        config_data = {
            'column_lines': sorted(self.column_lines),
            'row_lines': sorted(self.row_lines),
            'page_width': self.page_width,
            'page_height': self.page_height,
            'page_num': self.page_num,
            'zoom_factor': self.zoom_factor
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            self.update_save_status(True)
        except Exception as e:
            print(f'Error al guardar configuración: {e}')
    
    def load_saved_config(self):
        """Carga la configuración genérica guardada si existe"""
        config_path = self.get_config_file_path()
        if not os.path.exists(config_path):
            return False
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            self.column_lines = config_data.get('column_lines', [])
            self.row_lines = config_data.get('row_lines', [])
            
            # Restaurar zoom si estaba guardado
            saved_zoom = config_data.get('zoom_factor', 1.0)
            self.zoom_slider.setValue(int(saved_zoom * 100))
            
            # Actualizar las líneas en la vista
            self.update_lines()
            self.update_save_status(True)
            
            return True
        except Exception as e:
            print(f'Error al cargar configuración: {e}')
            return False
    
    def update_save_status(self, saved=True):
        """Actualiza el indicador de estado de guardado"""
        if saved:
            self.info_label.setText('✅ Configuración guardada automáticamente')
            self.info_label.setStyleSheet('color: green; font-style: italic;')
        else:
            self.info_label.setText('Haz clic en la imagen para añadir líneas. Clic derecho para eliminar.')
            self.info_label.setStyleSheet('color: #666; font-style: italic;')
    
    def closeEvent(self, event):
        """Cerrar el documento PDF al cerrar el diálogo"""
        # Guardar automáticamente antes de cerrar
        self.save_config()
        if self.pdf_doc:
            self.pdf_doc.close()
        event.accept()


class PDFReferenceDetector(QMainWindow):
    
    # Patrones de referencias predefinidos
    # Formato: (nombre, patrón_regex, ejemplo, descripción de grupos)
    REFERENCE_PATTERNS = {
        'Estilo /1.0-A': {
            'pattern': r'/\s*(\d+)[.\s]+(\d+|[A-Za-z]+)\s*[-/]\s*([A-Za-z0-9]+)',
            'example': '/1.0-A, /10.5-Z, /3.12-AB',
            'groups': ('página', 'columna', 'fila'),
            'order': 'página.columna-fila'
        },
        'Estilo 25-A.0': {
            'pattern': r'(\d+)\s*[-]\s*([A-Za-z]+)[.\s]+(\d+)',
            'example': '25-A.0, 10-B.5, 3-C.12',
            'groups': ('página', 'fila', 'columna'),
            'order': 'página-fila.columna'
        },
        'Estilo A1/25': {
            'pattern': r'([A-Za-z]+)(\d+)\s*[/]\s*(\d+)',
            'example': 'A1/25, B5/10, C12/3',
            'groups': ('fila', 'columna', 'página'),
            'order': 'fila+columna/página'
        },
        'Estilo (1-A-0)': {
            'pattern': r'\(\s*(\d+)\s*[-]\s*([A-Za-z]+)\s*[-]\s*(\d+)\s*\)',
            'example': '(1-A-0), (10-B-5), (3-C-12)',
            'groups': ('página', 'fila', 'columna'),
            'order': '(página-fila-columna)'
        },
        'Personalizado': {
            'pattern': '',
            'example': 'Define tu propio patrón regex',
            'groups': ('grupo1', 'grupo2', 'grupo3'),
            'order': 'personalizado'
        }
    }
    
    def __init__(self):
        super().__init__()
        self.pdf_path = None
        self.pdf_paths = []  # Lista de PDFs cargados
        self.references = []
        self.all_references = {}  # Referencias por PDF: {path: [referencias]}
        self.pdf_document = None
        self.current_pattern = 'Estilo /1.0-A'  # Patrón por defecto
        self.custom_pattern = ''
        # Posiciones exactas de columnas y filas (detectadas del cajetín)
        self.column_positions = []  # Lista de posiciones X de cada columna
        self.row_positions = []     # Lista de posiciones Y de cada fila
        self.grid_detected = False  # Si se detectó la cuadrícula
        self.init_ui()
        # Cargar configuración de cuadrícula genérica si existe
        self.load_saved_grid_config()
    
    def closeEvent(self, event):
        """Cerrar el documento PDF al cerrar la aplicación"""
        if self.pdf_document:
            self.pdf_document.close()
        event.accept()
        
    def get_javascript_code(self):
        """Genera el código JavaScript con los parámetros de estilo seleccionados"""
        color = self.get_highlight_color()
        line_width = self.line_width_spinbox.value()
        blink_speed = self.get_blink_speed()
        duration = self.get_highlight_duration()
        
        # Obtener nuevas opciones de estilo
        fill_style = self.fill_combo.currentText()
        fill_color = self.get_fill_color()
        animation_type = self.animation_combo.currentText()
        margin = self.rect_margin_spinbox.value()
        
        # Configurar el estilo de relleno
        fill_code = ""
        if fill_style == 'Semitransparente':
            fill_code = f"f.fillColor = {fill_color};"
        elif fill_style == 'Sólido':
            fill_code = f"f.fillColor = {fill_color};"
        
        # Aplicar margen a las coordenadas
        margin_code = ""
        if margin != 0:
            margin_code = f"""
    coordinates[0] -= {margin};
    coordinates[1] -= {margin};
    coordinates[2] += {margin};
    coordinates[3] += {margin};"""
        
        # Configurar el estilo de línea (para JavaScript de Acrobat es limitado)
        line_style = self.line_style_combo.currentText()
        line_style_code = ""
        if line_style == 'Discontinua':
            line_style_code = "f.borderStyle = border.d;"  # Dashed
        elif line_style == 'Punteada':
            line_style_code = "f.borderStyle = border.d;"  # Similar a dashed
        
        # Generar código de animación según el tipo
        if animation_type == 'Sin animación' or blink_speed == 0:
            blinker_code = "// Sin animación"
            interval_code = ""
        elif animation_type == 'Fade In/Out':
            blinker_code = """var f = getField('Target');
    if (f != null) {
        var oldDirty = dirty;
        // Fade effect simulado con visibilidad
        if (interval.counter++%2) { f.hidden=false; }
        else { f.hidden = true; }
        dirty = oldDirty;
    }"""
            interval_code = f"interval = app.setInterval('blinker()', {blink_speed});\n    interval.counter = 0;"
        elif animation_type == 'Pulso':
            blinker_code = """var f = getField('Target');
    if (f != null) {
        var oldDirty = dirty;
        // Efecto pulso
        if (interval.counter++%2) { f.hidden=false; }
        else { f.hidden = true; }
        dirty = oldDirty;
    }"""
            interval_code = f"interval = app.setInterval('blinker()', {blink_speed});\n    interval.counter = 0;"
        else:  # Parpadeo normal
            blinker_code = """var f = getField('Target');
    if (f != null) {
        var oldDirty = dirty;
        if (interval.counter++%2) { f.hidden=false; }
        else { f.hidden = true; }
        dirty = oldDirty;
    }"""
            interval_code = f"interval = app.setInterval('blinker()', {blink_speed});\n    interval.counter = 0;"
        
        return f"""
function finish() {{
    app.clearInterval(interval);
    var oldDirty = dirty;
    removeField('Target');
    dirty = oldDirty;
}}

function blinker() {{
    {blinker_code}
}}

function highlight(page, coordinates) {{
    var f = getField('Target');
    if (f != null) {{
        app.clearTimeOut(timer);
        finish();
    }}{margin_code}
    var oldDirty = dirty;
    var f = addField('Target', 'button', page, coordinates);
    f.lineWidth = {line_width};
    f.strokeColor = {color};
    {fill_code}
    {line_style_code}
    dirty = oldDirty;
    {interval_code}
    timer = app.setTimeOut('finish()', {duration});
}}
"""
        
    def init_ui(self):
        self.setWindowTitle('PDF Reference Detector')
        self.setGeometry(100, 100, 1300, 850)
        
        # Establecer icono de la aplicación
        icon_path = os.path.join(get_app_path(), 'logo.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Habilitar drag & drop
        self.setAcceptDrops(True)
        
        # Estilo global de la aplicación - Tema oscuro elegante
        self.setStyleSheet('''
            QMainWindow {
                background-color: #0f172a;
            }
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QLabel {
                color: #cbd5e1;
                background: transparent;
            }
            QGroupBox {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                margin-top: 20px;
                padding: 15px;
                padding-top: 25px;
                font-weight: bold;
                font-size: 13px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 15px;
                top: 5px;
                padding: 2px 10px;
                background-color: #1e293b;
                color: #60a5fa;
                border-radius: 4px;
            }
            QLineEdit {
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 12px;
                color: #f1f5f9;
                selection-background-color: #3b82f6;
            }
            QLineEdit:focus {
                border: 2px solid #3b82f6;
            }
            QLineEdit:disabled {
                background-color: #1e293b;
                color: #64748b;
            }
            QSpinBox {
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 6px 10px;
                color: #f1f5f9;
                min-width: 60px;
            }
            QSpinBox:focus {
                border: 2px solid #3b82f6;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #334155;
                border: none;
                width: 20px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #475569;
            }
            QComboBox {
                background-color: #0f172a;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 12px;
                color: #f1f5f9;
                min-width: 120px;
            }
            QComboBox:focus {
                border: 2px solid #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #94a3b8;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e293b;
                border: 1px solid #475569;
                color: #f1f5f9;
                selection-background-color: #3b82f6;
                outline: none;
            }
            QTableWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                gridline-color: #334155;
                color: #e2e8f0;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #334155;
            }
            QTableWidget::item:selected {
                background-color: #3b82f6;
                color: white;
            }
            QTableWidget::item:alternate {
                background-color: #0f172a;
            }
            QHeaderView::section {
                background-color: #334155;
                color: #e2e8f0;
                padding: 12px;
                border: none;
                border-bottom: 2px solid #3b82f6;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #e2e8f0;
                padding: 10px;
            }
            QScrollBar:vertical {
                background-color: #1e293b;
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #475569;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #64748b;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QStatusBar {
                background-color: #1e293b;
                color: #94a3b8;
                border-top: 1px solid #334155;
                padding: 5px;
            }
            QSplitter::handle {
                background-color: #334155;
                height: 2px;
            }
            QSplitter::handle:hover {
                background-color: #3b82f6;
            }
        ''')
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Pestañas principales (arriba del todo)
        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet('''
            QTabWidget::pane {
                background-color: #0f172a;
                border: none;
                padding: 15px;
            }
            QTabBar {
                background-color: #1e293b;
            }
            QTabBar::tab {
                background-color: #1e293b;
                color: #64748b;
                padding: 14px 30px;
                margin: 0px;
                border: none;
                border-bottom: 3px solid transparent;
                font-weight: bold;
                font-size: 14px;
            }
            QTabBar::tab:selected {
                background-color: #0f172a;
                color: #60a5fa;
                border-bottom: 3px solid #3b82f6;
            }
            QTabBar::tab:hover:!selected {
                background-color: #334155;
                color: #e2e8f0;
            }
        ''')
        
        # ==================== PESTAÑA 1: CONFIGURACIÓN ====================
        config_page = QWidget()
        config_layout = QVBoxLayout(config_page)
        config_layout.setSpacing(15)
        config_layout.setContentsMargins(10, 10, 10, 10)
        
        # Header con título y estado
        header = QWidget()
        header.setStyleSheet('background-color: transparent;')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(5, 0, 5, 10)
        
        title_label = QLabel('⚡ Configuración del Detector')
        title_label.setStyleSheet('''
            font-size: 18px;
            font-weight: bold;
            color: #f1f5f9;
        ''')
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        self.config_status = QLabel('○ Sin configuración de cuadrícula')
        self.config_status.setStyleSheet('''
            color: #64748b;
            font-size: 12px;
            padding: 6px 12px;
            border: 1px solid #334155;
            border-radius: 4px;
        ''')
        header_layout.addWidget(self.config_status)
        
        config_layout.addWidget(header)
        
        # Sección de archivos con zona de arrastrar
        file_group = QGroupBox('📁 Archivos PDF (múltiples)')
        file_main_layout = QVBoxLayout(file_group)
        file_main_layout.setSpacing(10)
        
        # Zona de drag & drop
        self.drop_zone = QLabel('📥 Arrastra uno o varios PDFs aquí')
        self.drop_zone.setAlignment(Qt.AlignCenter)
        self.drop_zone.setStyleSheet('''
            padding: 20px;
            background-color: #0f172a;
            border: 2px dashed #334155;
            border-radius: 10px;
            color: #64748b;
            font-size: 14px;
        ''')
        self.drop_zone.setMinimumHeight(60)
        file_main_layout.addWidget(self.drop_zone)
        
        # Lista de PDFs cargados
        pdf_list_layout = QHBoxLayout()
        
        self.pdf_list = QListWidget()
        self.pdf_list.setStyleSheet('''
            QListWidget {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #e2e8f0;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #334155;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #1e293b;
            }
        ''')
        self.pdf_list.setMaximumHeight(120)
        self.pdf_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        pdf_list_layout.addWidget(self.pdf_list, 1)
        
        # Botones de lista
        list_buttons = QVBoxLayout()
        list_buttons.setSpacing(5)
        
        self.clear_list_btn = QPushButton('🗑️')
        self.clear_list_btn.setToolTip('Limpiar lista')
        self.clear_list_btn.setFixedSize(35, 35)
        self.clear_list_btn.clicked.connect(self.clear_pdf_list)
        self.clear_list_btn.setStyleSheet('''
            QPushButton {
                background-color: #dc2626;
                color: white;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #ef4444;
            }
        ''')
        list_buttons.addWidget(self.clear_list_btn)
        
        self.remove_selected_btn = QPushButton('➖')
        self.remove_selected_btn.setToolTip('Eliminar seleccionados')
        self.remove_selected_btn.setFixedSize(35, 35)
        self.remove_selected_btn.clicked.connect(self.remove_selected_pdfs)
        self.remove_selected_btn.setStyleSheet('''
            QPushButton {
                background-color: #f59e0b;
                color: white;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #fbbf24;
            }
        ''')
        list_buttons.addWidget(self.remove_selected_btn)
        list_buttons.addStretch()
        
        pdf_list_layout.addLayout(list_buttons)
        file_main_layout.addLayout(pdf_list_layout)
        
        # Contador de PDFs
        self.pdf_count_label = QLabel('0 archivos cargados')
        self.pdf_count_label.setStyleSheet('color: #64748b; font-size: 12px;')
        file_main_layout.addWidget(self.pdf_count_label)
        
        # Fila de botones principales
        file_row = QHBoxLayout()
        file_row.setSpacing(12)
        
        self.select_button = QPushButton('📂 Seleccionar PDFs')
        self.select_button.clicked.connect(self.select_pdf)
        self.select_button.setStyleSheet('''
            QPushButton {
                background-color: #10b981;
                color: white;
                padding: 10px 18px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #34d399;
            }
        ''')
        file_row.addWidget(self.select_button)
        
        self.detect_button = QPushButton('🔍 Detectar en Todos')
        self.detect_button.clicked.connect(self.detect_references)
        self.detect_button.setEnabled(False)
        self.detect_button.setStyleSheet('''
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 10px 18px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #60a5fa;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #64748b;
            }
        ''')
        file_row.addWidget(self.detect_button)
        
        self.generate_button = QPushButton('✨ Generar Todos los PDFs')
        self.generate_button.clicked.connect(self.generate_interactive_pdf)
        self.generate_button.setEnabled(False)
        self.generate_button.setStyleSheet('''
            QPushButton {
                background-color: #f59e0b;
                color: #0f172a;
                padding: 10px 18px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #fbbf24;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #64748b;
            }
        ''')
        file_row.addWidget(self.generate_button)
        
        file_row.addStretch()
        file_main_layout.addLayout(file_row)
        
        # Opciones de guardado
        save_options_row = QHBoxLayout()
        
        self.keep_original_name = QCheckBox('Mantener nombre original (sobrescribir)')
        self.keep_original_name.setStyleSheet('color: #94a3b8;')
        self.keep_original_name.setToolTip('Si está marcado, el PDF se guardará con el mismo nombre (sobrescribiendo el original)')
        save_options_row.addWidget(self.keep_original_name)
        
        save_options_row.addSpacing(20)
        
        self.disable_popups = QCheckBox('Desactivar ventanas emergentes al exportar')
        self.disable_popups.setStyleSheet('color: #94a3b8;')
        self.disable_popups.setToolTip('Si está marcado, no se mostrarán ventanas emergentes de confirmación al terminar de exportar')
        save_options_row.addWidget(self.disable_popups)
        
        save_options_row.addStretch()
        file_main_layout.addLayout(save_options_row)
        
        config_layout.addWidget(file_group)
        
        # Variable para compatibilidad (primer PDF de la lista)
        self.file_label = QLabel()  # Hidden, for compatibility
        
        # Contenedor horizontal para las dos columnas de configuración
        config_container = QHBoxLayout()
        config_container.setSpacing(15)
        
        # Columna izquierda: Patrón y Cuadrícula
        left_column = QVBoxLayout()
        
        # Sección de selección de patrón
        pattern_group = QGroupBox('🔤 Estilo de Referencias')
        pattern_layout = QVBoxLayout(pattern_group)
        pattern_layout.setSpacing(10)
        
        pattern_row1 = QHBoxLayout()
        lbl_estilo = QLabel('Estilo:')
        lbl_estilo.setStyleSheet('color: #94a3b8; min-width: 50px;')
        pattern_row1.addWidget(lbl_estilo)
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems(list(self.REFERENCE_PATTERNS.keys()))
        self.pattern_combo.currentTextChanged.connect(self.on_pattern_changed)
        self.pattern_combo.setMinimumWidth(160)
        pattern_row1.addWidget(self.pattern_combo)
        
        pattern_row1.addSpacing(15)
        lbl_ejemplo = QLabel('Ejemplo:')
        lbl_ejemplo.setStyleSheet('color: #94a3b8;')
        pattern_row1.addWidget(lbl_ejemplo)
        self.pattern_example = QLabel(self.REFERENCE_PATTERNS['Estilo /1.0-A']['example'])
        self.pattern_example.setStyleSheet('''
            color: #60a5fa;
            font-style: italic;
            padding: 4px 8px;
            background-color: #0f172a;
            border-radius: 4px;
        ''')
        pattern_row1.addWidget(self.pattern_example)
        pattern_row1.addStretch()
        
        self.help_pattern_button = QPushButton('?')
        self.help_pattern_button.setFixedSize(28, 28)
        self.help_pattern_button.clicked.connect(self.show_pattern_help)
        self.help_pattern_button.setStyleSheet('''
            QPushButton {
                background-color: #334155;
                color: #94a3b8;
                border-radius: 14px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: white;
            }
        ''')
        pattern_row1.addWidget(self.help_pattern_button)
        pattern_layout.addLayout(pattern_row1)
        
        # Fila para patrón personalizado con formato simple
        pattern_row2 = QHBoxLayout()
        lbl_patron = QLabel('Patrón:')
        lbl_patron.setStyleSheet('color: #94a3b8; min-width: 50px;')
        pattern_row2.addWidget(lbl_patron)
        self.custom_pattern_input = QLineEdit()
        self.custom_pattern_input.setPlaceholderText('Ej: /{P}.{C}-{F}  o  {P}-{F}.{C}')
        self.custom_pattern_input.setEnabled(False)
        self.custom_pattern_input.textChanged.connect(self.on_custom_pattern_changed)
        self.custom_pattern_input.setToolTip(
            'Usa estos placeholders:\n'
            '  {P} = Página (número)\n'
            '  {C} = Columna (número)\n'
            '  {F} = Fila (letra A-Z)\n\n'
            'Ejemplo: /{P}.{C}-{F} detecta /5.3-A'
        )
        pattern_row2.addWidget(self.custom_pattern_input, 1)
        pattern_layout.addLayout(pattern_row2)
        
        # Indicador de placeholders
        self.pattern_hint = QLabel('💡 Usa: {P}=página  {C}=columna  {F}=fila')
        self.pattern_hint.setStyleSheet('''
            color: #64748b;
            font-size: 11px;
            padding: 2px 0;
            margin-left: 55px;
        ''')
        self.pattern_hint.hide()  # Oculto hasta que se seleccione Personalizado
        pattern_layout.addWidget(self.pattern_hint)
        
        # Preview del patrón resultante
        self.pattern_preview_label = QLabel('')
        self.pattern_preview_label.setStyleSheet('''
            color: #10b981;
            font-size: 11px;
            font-family: 'Consolas', monospace;
            padding: 2px 0;
            margin-left: 55px;
        ''')
        self.pattern_preview_label.hide()
        pattern_layout.addWidget(self.pattern_preview_label)
        
        left_column.addWidget(pattern_group)
        
        # Sección de configuración de cuadrícula
        grid_group = QGroupBox('📐 Configuración de Cuadrícula')
        grid_main_layout = QVBoxLayout(grid_group)
        grid_main_layout.setSpacing(10)
        
        grid_row1 = QHBoxLayout()
        lbl_cols = QLabel('Columnas:')
        lbl_cols.setStyleSheet('color: #94a3b8;')
        grid_row1.addWidget(lbl_cols)
        self.cols_spinbox = QSpinBox()
        self.cols_spinbox.setRange(1, 50)
        self.cols_spinbox.setValue(10)
        self.cols_spinbox.valueChanged.connect(self.update_size_placeholders)
        grid_row1.addWidget(self.cols_spinbox)
        
        grid_row1.addSpacing(15)
        lbl_rows = QLabel('Filas:')
        lbl_rows.setStyleSheet('color: #94a3b8;')
        grid_row1.addWidget(lbl_rows)
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setRange(1, 26)
        self.rows_spinbox.setValue(8)
        self.rows_spinbox.valueChanged.connect(self.update_rows_info)
        self.rows_spinbox.valueChanged.connect(self.update_size_placeholders)
        grid_row1.addWidget(self.rows_spinbox)
        
        self.rows_info_label = QLabel('(A-H)')
        self.rows_info_label.setStyleSheet('color: #60a5fa; font-size: 12px;')
        grid_row1.addWidget(self.rows_info_label)
        
        grid_row1.addStretch()
        
        # Botón Editor Visual
        self.visual_editor_button = QPushButton('🎨 Editor Visual')
        self.visual_editor_button.clicked.connect(self.open_visual_editor)
        self.visual_editor_button.setEnabled(False)
        self.visual_editor_button.setStyleSheet('''
            QPushButton {
                background-color: #8b5cf6;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #a78bfa;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #64748b;
            }
        ''')
        grid_row1.addWidget(self.visual_editor_button)
        grid_main_layout.addLayout(grid_row1)
        
        grid_row2 = QHBoxLayout()
        lbl_marg_l = QLabel('Margen Izq:')
        lbl_marg_l.setStyleSheet('color: #94a3b8;')
        grid_row2.addWidget(lbl_marg_l)
        self.margin_left_spinbox = QSpinBox()
        self.margin_left_spinbox.setRange(0, 30)
        self.margin_left_spinbox.setValue(5)
        self.margin_left_spinbox.setSuffix('%')
        grid_row2.addWidget(self.margin_left_spinbox)
        
        grid_row2.addSpacing(15)
        lbl_marg_t = QLabel('Margen Sup:')
        lbl_marg_t.setStyleSheet('color: #94a3b8;')
        grid_row2.addWidget(lbl_marg_t)
        self.margin_top_spinbox = QSpinBox()
        self.margin_top_spinbox.setRange(0, 30)
        self.margin_top_spinbox.setValue(5)
        self.margin_top_spinbox.setSuffix('%')
        grid_row2.addWidget(self.margin_top_spinbox)
        grid_row2.addStretch()
        grid_main_layout.addLayout(grid_row2)
        
        grid_row3 = QHBoxLayout()
        lbl_ancho = QLabel('Anchos:')
        lbl_ancho.setStyleSheet('color: #94a3b8; min-width: 50px;')
        grid_row3.addWidget(lbl_ancho)
        self.col_sizes_input = QLineEdit()
        self.col_sizes_input.setPlaceholderText('1,1,1,1... (valores relativos)')
        grid_row3.addWidget(self.col_sizes_input, 1)
        grid_main_layout.addLayout(grid_row3)
        
        grid_row4 = QHBoxLayout()
        lbl_altos = QLabel('Altos:')
        lbl_altos.setStyleSheet('color: #94a3b8; min-width: 50px;')
        grid_row4.addWidget(lbl_altos)
        self.row_sizes_input = QLineEdit()
        self.row_sizes_input.setPlaceholderText('1,1,1,1... (valores relativos)')
        grid_row4.addWidget(self.row_sizes_input, 1)
        grid_main_layout.addLayout(grid_row4)
        
        # Página a escanear (oculto, se mantiene para compatibilidad)
        self.scan_page_spinbox = QSpinBox()
        self.scan_page_spinbox.setRange(1, 999)
        self.scan_page_spinbox.setValue(2)
        self.scan_page_spinbox.setVisible(False)
        
        left_column.addWidget(grid_group)
        config_container.addLayout(left_column, 1)
        
        # Columna derecha: Configuración del rectángulo de resaltado
        right_column = QVBoxLayout()
        
        highlight_group = QGroupBox('🎯 Estilo del Rectángulo')
        highlight_layout = QVBoxLayout(highlight_group)
        highlight_layout.setSpacing(12)
        
        # Color y grosor
        color_row = QHBoxLayout()
        lbl_color = QLabel('Color:')
        lbl_color.setStyleSheet('color: #94a3b8;')
        color_row.addWidget(lbl_color)
        self.color_combo = QComboBox()
        self.color_combo.addItems(['Rojo', 'Verde', 'Azul', 'Amarillo', 'Naranja', 'Magenta', 'Cian'])
        self.color_combo.setCurrentText('Rojo')
        color_row.addWidget(self.color_combo)
        
        color_row.addSpacing(20)
        lbl_grosor = QLabel('Grosor:')
        lbl_grosor.setStyleSheet('color: #94a3b8;')
        color_row.addWidget(lbl_grosor)
        self.line_width_spinbox = QSpinBox()
        self.line_width_spinbox.setRange(1, 10)
        self.line_width_spinbox.setValue(3)
        self.line_width_spinbox.setSuffix(' px')
        color_row.addWidget(self.line_width_spinbox)
        color_row.addStretch()
        highlight_layout.addLayout(color_row)
        
        # Estilo de línea y parpadeo
        style_row = QHBoxLayout()
        lbl_estilo = QLabel('Línea:')
        lbl_estilo.setStyleSheet('color: #94a3b8;')
        style_row.addWidget(lbl_estilo)
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(['Sólida', 'Discontinua', 'Punteada'])
        style_row.addWidget(self.line_style_combo)
        
        style_row.addSpacing(20)
        lbl_parpadeo = QLabel('Parpadeo:')
        lbl_parpadeo.setStyleSheet('color: #94a3b8;')
        style_row.addWidget(lbl_parpadeo)
        self.blink_speed_combo = QComboBox()
        self.blink_speed_combo.addItems(['Rápido', 'Normal', 'Lento', 'Sin parpadeo'])
        self.blink_speed_combo.setCurrentText('Normal')
        style_row.addWidget(self.blink_speed_combo)
        style_row.addStretch()
        highlight_layout.addLayout(style_row)
        
        # Duración y relleno
        fill_row = QHBoxLayout()
        lbl_duracion = QLabel('Duración:')
        lbl_duracion.setStyleSheet('color: #94a3b8;')
        fill_row.addWidget(lbl_duracion)
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setRange(1, 30)
        self.duration_spinbox.setValue(5)
        self.duration_spinbox.setSuffix(' seg')
        fill_row.addWidget(self.duration_spinbox)
        
        fill_row.addSpacing(20)
        lbl_relleno = QLabel('Relleno:')
        lbl_relleno.setStyleSheet('color: #94a3b8;')
        fill_row.addWidget(lbl_relleno)
        self.fill_combo = QComboBox()
        self.fill_combo.addItems(['Sin relleno', 'Semitransparente', 'Sólido'])
        fill_row.addWidget(self.fill_combo)
        fill_row.addStretch()
        highlight_layout.addLayout(fill_row)
        
        # Tipo de animación y opacidad
        anim_row = QHBoxLayout()
        lbl_anim = QLabel('Animación:')
        lbl_anim.setStyleSheet('color: #94a3b8;')
        anim_row.addWidget(lbl_anim)
        self.animation_combo = QComboBox()
        self.animation_combo.addItems(['Parpadeo', 'Fade In/Out', 'Pulso', 'Sin animación'])
        self.animation_combo.setCurrentText('Parpadeo')
        anim_row.addWidget(self.animation_combo)
        
        anim_row.addSpacing(20)
        lbl_opacidad = QLabel('Opacidad:')
        lbl_opacidad.setStyleSheet('color: #94a3b8;')
        anim_row.addWidget(lbl_opacidad)
        self.opacity_spinbox = QSpinBox()
        self.opacity_spinbox.setRange(10, 100)
        self.opacity_spinbox.setValue(100)
        self.opacity_spinbox.setSuffix(' %')
        self.opacity_spinbox.setToolTip('Opacidad del borde (100% = totalmente visible)')
        anim_row.addWidget(self.opacity_spinbox)
        anim_row.addStretch()
        highlight_layout.addLayout(anim_row)
        
        # Color de relleno y esquinas
        extra_row = QHBoxLayout()
        lbl_fill_color = QLabel('Color relleno:')
        lbl_fill_color.setStyleSheet('color: #94a3b8;')
        extra_row.addWidget(lbl_fill_color)
        self.fill_color_combo = QComboBox()
        self.fill_color_combo.addItems(['Mismo que borde', 'Rojo', 'Verde', 'Azul', 'Amarillo', 'Naranja', 'Magenta', 'Cian', 'Blanco', 'Negro'])
        self.fill_color_combo.setToolTip('Color del relleno (si está habilitado)')
        extra_row.addWidget(self.fill_color_combo)
        
        extra_row.addSpacing(20)
        lbl_corners = QLabel('Esquinas:')
        lbl_corners.setStyleSheet('color: #94a3b8;')
        extra_row.addWidget(lbl_corners)
        self.corner_radius_spinbox = QSpinBox()
        self.corner_radius_spinbox.setRange(0, 20)
        self.corner_radius_spinbox.setValue(0)
        self.corner_radius_spinbox.setSuffix(' px')
        self.corner_radius_spinbox.setToolTip('Radio de las esquinas redondeadas (0 = cuadradas)')
        extra_row.addWidget(self.corner_radius_spinbox)
        extra_row.addStretch()
        highlight_layout.addLayout(extra_row)
        
        # Margen y efecto
        margin_row = QHBoxLayout()
        lbl_margin = QLabel('Margen:')
        lbl_margin.setStyleSheet('color: #94a3b8;')
        margin_row.addWidget(lbl_margin)
        self.rect_margin_spinbox = QSpinBox()
        self.rect_margin_spinbox.setRange(-20, 20)
        self.rect_margin_spinbox.setValue(0)
        self.rect_margin_spinbox.setSuffix(' px')
        self.rect_margin_spinbox.setToolTip('Margen del rectángulo (negativo = más pequeño, positivo = más grande)')
        margin_row.addWidget(self.rect_margin_spinbox)
        
        margin_row.addSpacing(20)
        lbl_effect = QLabel('Efecto:')
        lbl_effect.setStyleSheet('color: #94a3b8;')
        margin_row.addWidget(lbl_effect)
        self.effect_combo = QComboBox()
        self.effect_combo.addItems(['Ninguno', 'Sombra suave', 'Resplandor'])
        self.effect_combo.setToolTip('Efecto visual adicional')
        margin_row.addWidget(self.effect_combo)
        margin_row.addStretch()
        highlight_layout.addLayout(margin_row)
        
        # Preview del estilo
        preview_frame = QFrame()
        preview_frame.setStyleSheet('''
            QFrame {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px;
            }
        ''')
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 8, 10, 8)
        
        preview_label = QLabel('Vista previa:')
        preview_label.setStyleSheet('color: #64748b; font-size: 11px;')
        preview_layout.addWidget(preview_label)
        
        self.style_preview = QLabel('████████████████████')
        self.style_preview.setStyleSheet('''
            color: #ef4444;
            font-size: 20px;
            font-weight: bold;
            letter-spacing: 2px;
        ''')
        self.style_preview.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.style_preview)
        
        highlight_layout.addWidget(preview_frame)
        
        # Conectar cambios de estilos al guardado automático
        self.color_combo.currentTextChanged.connect(self.update_style_preview)
        self.line_width_spinbox.valueChanged.connect(self.save_styles_config)
        self.line_style_combo.currentTextChanged.connect(self.save_styles_config)
        self.blink_speed_combo.currentTextChanged.connect(self.save_styles_config)
        self.duration_spinbox.valueChanged.connect(self.save_styles_config)
        self.fill_combo.currentTextChanged.connect(self.save_styles_config)
        self.animation_combo.currentTextChanged.connect(self.save_styles_config)
        self.opacity_spinbox.valueChanged.connect(self.save_styles_config)
        self.fill_color_combo.currentTextChanged.connect(self.save_styles_config)
        self.corner_radius_spinbox.valueChanged.connect(self.save_styles_config)
        self.rect_margin_spinbox.valueChanged.connect(self.save_styles_config)
        self.effect_combo.currentTextChanged.connect(self.save_styles_config)
        self.pattern_combo.currentTextChanged.connect(self.save_styles_config)
        self.custom_pattern_input.textChanged.connect(self.save_styles_config)
        self.keep_original_name.stateChanged.connect(self.save_styles_config)
        self.disable_popups.stateChanged.connect(self.save_styles_config)
        
        right_column.addWidget(highlight_group)
        right_column.addStretch()
        
        config_container.addLayout(right_column, 1)
        config_layout.addLayout(config_container)
        config_layout.addStretch()
        
        # Añadir página de Configuración como widget central (sin pestañas)
        main_layout.addWidget(config_page)
        
        # Crear widgets ocultos para tabla y estadísticas (usados en diálogos)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['Referencia', 'Página', 'Columna', 'Fila', 'Contexto'])
        
        self.ref_count_label = QLabel('0 referencias')
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setText('Carga un PDF y detecta las referencias para ver las estadísticas.')
        
        # Ocultar el tab widget ya que no lo usaremos
        self.main_tabs.hide()
        
        # ==================== BOTÓN DE ENGRANAJE (esquina inferior derecha) ====================
        self.info_button = QPushButton('⚙')
        self.info_button.setFixedSize(50, 50)
        self.info_button.setStyleSheet('''
            QPushButton {
                background-color: #3b82f6;
                color: white;
                font-size: 22px;
                border-radius: 25px;
                border: none;
            }
            QPushButton:hover {
                background-color: #60a5fa;
            }
            QPushButton::menu-indicator {
                width: 0px;
            }
        ''')
        
        # Menú para el botón
        info_menu = QMenu(self)
        info_menu.setStyleSheet('''
            QMenu {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                color: #e2e8f0;
                padding: 10px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
            }
        ''')
        info_menu.addAction('📋 Ver Referencias', self.show_references_dialog)
        info_menu.addAction('📊 Ver Estadísticas', self.show_statistics_dialog)
        
        self.info_button.setMenu(info_menu)
        
        # Posicionar botón en esquina inferior derecha
        main_layout.addWidget(self.info_button, 0, Qt.AlignRight | Qt.AlignBottom)
        
        # Barra de estado
        self.statusBar().showMessage('⚡ Listo - Arrastra un PDF o haz clic en Seleccionar')
    
    def dragEnterEvent(self, event):
        """Maneja cuando archivos entran en la zona de drop"""
        if event.mimeData().hasUrls():
            # Verificar si hay al menos un PDF
            has_pdf = any(url.toLocalFile().lower().endswith('.pdf') 
                        for url in event.mimeData().urls())
            if has_pdf:
                event.acceptProposedAction()
                self.drop_zone.setStyleSheet('''
                    padding: 20px;
                    background-color: #1e3a5f;
                    border: 2px dashed #3b82f6;
                    border-radius: 10px;
                    color: #60a5fa;
                    font-size: 14px;
                ''')
                self.drop_zone.setText('📥 Suelta los PDFs aquí')
            else:
                event.ignore()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Maneja cuando archivos salen de la zona de drop"""
        self.reset_drop_zone()
    
    def dropEvent(self, event):
        """Maneja cuando se sueltan archivos"""
        urls = event.mimeData().urls()
        pdf_files = [url.toLocalFile() for url in urls 
                    if url.toLocalFile().lower().endswith('.pdf')]
        
        if pdf_files:
            self.add_pdf_files(pdf_files)
        
        self.reset_drop_zone()
    
    def reset_drop_zone(self):
        """Restaura el estilo de la zona de drop"""
        self.drop_zone.setStyleSheet('''
            padding: 20px;
            background-color: #0f172a;
            border: 2px dashed #334155;
            border-radius: 10px;
            color: #64748b;
            font-size: 14px;
        ''')
        self.drop_zone.setText('📥 Arrastra uno o varios PDFs aquí')
    
    def add_pdf_files(self, file_paths):
        """Añade archivos PDF a la lista"""
        added = 0
        for file_path in file_paths:
            if file_path not in self.pdf_paths:
                self.pdf_paths.append(file_path)
                item = QListWidgetItem(f'📄 {os.path.basename(file_path)}')
                item.setData(Qt.UserRole, file_path)
                self.pdf_list.addItem(item)
                added += 1
        
        if added > 0:
            self.update_pdf_count()
            self.detect_button.setEnabled(True)
            self.visual_editor_button.setEnabled(True)
            
            # Establecer el primer PDF como el activo para el editor visual
            if self.pdf_paths:
                self.pdf_path = self.pdf_paths[0]
            
            self.statusBar().showMessage(f'✅ {added} PDF(s) añadido(s). Total: {len(self.pdf_paths)}')
            
            # Cargar configuración de cuadrícula
            self.load_saved_grid_config()
    
    def update_pdf_count(self):
        """Actualiza el contador de PDFs"""
        count = len(self.pdf_paths)
        if count == 0:
            self.pdf_count_label.setText('0 archivos cargados')
            self.pdf_count_label.setStyleSheet('color: #64748b; font-size: 12px;')
        elif count == 1:
            self.pdf_count_label.setText('1 archivo cargado')
            self.pdf_count_label.setStyleSheet('color: #10b981; font-size: 12px;')
        else:
            self.pdf_count_label.setText(f'{count} archivos cargados')
            self.pdf_count_label.setStyleSheet('color: #10b981; font-size: 12px;')
    
    def clear_pdf_list(self):
        """Limpia la lista de PDFs"""
        self.pdf_paths.clear()
        self.pdf_list.clear()
        self.all_references.clear()
        self.references.clear()
        self.pdf_path = None
        self.update_pdf_count()
        self.detect_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.table.setRowCount(0)
        self.ref_count_label.setText('0 referencias')
        self.statusBar().showMessage('Lista de PDFs limpiada')
    
    def remove_selected_pdfs(self):
        """Elimina los PDFs seleccionados de la lista"""
        selected_items = self.pdf_list.selectedItems()
        for item in selected_items:
            file_path = item.data(Qt.UserRole)
            if file_path in self.pdf_paths:
                self.pdf_paths.remove(file_path)
            if file_path in self.all_references:
                del self.all_references[file_path]
            self.pdf_list.takeItem(self.pdf_list.row(item))
        
        self.update_pdf_count()
        
        if not self.pdf_paths:
            self.detect_button.setEnabled(False)
            self.generate_button.setEnabled(False)
            self.pdf_path = None
        else:
            self.pdf_path = self.pdf_paths[0]
        
        self.statusBar().showMessage(f'{len(selected_items)} PDF(s) eliminado(s)')
        
    def select_pdf(self):
        """Permite al usuario seleccionar múltiples archivos PDF"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            'Seleccionar archivos PDF',
            '',
            'Archivos PDF (*.pdf)'
        )
        
        if file_paths:
            self.add_pdf_files(file_paths)
    
    def load_saved_grid_config(self):
        """Carga la configuración de cuadrícula genérica (aplica a todos los PDFs)"""
        # Usar archivo de configuración genérico
        app_dir = get_app_path()
        config_path = os.path.join(app_dir, 'grid_config.json')
        
        if not os.path.exists(config_path):
            # Resetear estado si no hay configuración
            self.grid_detected = False
            self.column_positions = []
            self.row_positions = []
            self.config_status.setText('○ Sin configuración')
            self.config_status.setStyleSheet('color: #94a3b8; font-size: 12px;')
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Cargar posiciones exactas
            self.column_positions = config_data.get('column_lines', [])
            self.row_positions = config_data.get('row_lines', [])
            self.grid_detected = len(self.column_positions) > 1 and len(self.row_positions) > 1
            
            if self.grid_detected:
                # Actualizar interfaz
                num_cols = len(self.column_positions) - 1
                num_rows = len(self.row_positions) - 1
                self.cols_spinbox.setValue(num_cols)
                self.rows_spinbox.setValue(num_rows)
                
                # Calcular tamaños relativos de columnas
                col_widths = []
                for i in range(len(self.column_positions) - 1):
                    col_widths.append(self.column_positions[i + 1] - self.column_positions[i])
                if col_widths:
                    min_width = min(col_widths)
                    if min_width > 0:
                        relative_cols = [round(w / min_width, 2) for w in col_widths]
                        self.col_sizes_input.setText(','.join(str(s) for s in relative_cols))
                
                # Calcular tamaños relativos de filas
                row_heights = []
                for i in range(len(self.row_positions) - 1):
                    row_heights.append(self.row_positions[i + 1] - self.row_positions[i])
                if row_heights:
                    min_height = min(row_heights)
                    if min_height > 0:
                        relative_rows = [round(h / min_height, 2) for h in row_heights]
                        self.row_sizes_input.setText(','.join(str(s) for s in relative_rows))
                
                # Calcular márgenes
                page_width = config_data.get('page_width', 0)
                page_height = config_data.get('page_height', 0)
                
                if page_width > 0 and self.column_positions:
                    margin_left_pct = int((self.column_positions[0] / page_width) * 100)
                    self.margin_left_spinbox.setValue(max(0, min(margin_left_pct, 30)))
                
                if page_height > 0 and self.row_positions:
                    margin_top_pct = int((self.row_positions[0] / page_height) * 100)
                    self.margin_top_spinbox.setValue(max(0, min(margin_top_pct, 30)))
                
                self.statusBar().showMessage(
                    f'✅ Configuración cargada: {num_cols} columnas × {num_rows} filas (cuadrantes exactos)'
                )
                self.config_status.setText(f'● {num_cols}×{num_rows} cuadrantes')
                self.config_status.setStyleSheet('''
                    color: #10b981;
                    font-size: 12px;
                    font-weight: bold;
                    background: transparent;
                    padding: 4px 10px;
                    border: 1px solid #10b981;
                    border-radius: 4px;
                ''')
        except Exception as e:
            print(f'Error al cargar configuración: {e}')
            self.grid_detected = False
            self.config_status.setText('○ Sin configuración')
            self.config_status.setStyleSheet('''
                color: #64748b;
                font-size: 12px;
                background: transparent;
                padding: 4px 10px;
                border: 1px solid #334155;
                border-radius: 4px;
            ''')
        
        # Cargar configuración de estilos
        self.load_styles_config()
    
    def load_styles_config(self):
        """Carga la configuración de estilos guardada"""
        app_dir = get_app_path()
        config_path = os.path.join(app_dir, 'styles_config.json')
        
        if not os.path.exists(config_path):
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Cargar patrón de referencia
            if 'pattern' in config:
                idx = self.pattern_combo.findText(config['pattern'])
                if idx >= 0:
                    self.pattern_combo.setCurrentIndex(idx)
            if 'custom_pattern' in config:
                self.custom_pattern_input.setText(config['custom_pattern'])
            
            # Cargar estilos del rectángulo
            if 'rect_color' in config:
                idx = self.color_combo.findText(config['rect_color'])
                if idx >= 0:
                    self.color_combo.setCurrentIndex(idx)
            if 'line_width' in config:
                self.line_width_spinbox.setValue(config['line_width'])
            if 'line_style' in config:
                idx = self.line_style_combo.findText(config['line_style'])
                if idx >= 0:
                    self.line_style_combo.setCurrentIndex(idx)
            if 'blink_speed' in config:
                idx = self.blink_speed_combo.findText(config['blink_speed'])
                if idx >= 0:
                    self.blink_speed_combo.setCurrentIndex(idx)
            if 'duration' in config:
                self.duration_spinbox.setValue(config['duration'])
            if 'fill_style' in config:
                idx = self.fill_combo.findText(config['fill_style'])
                if idx >= 0:
                    self.fill_combo.setCurrentIndex(idx)
            
            # Cargar nuevas opciones de estilo
            if 'animation_type' in config:
                idx = self.animation_combo.findText(config['animation_type'])
                if idx >= 0:
                    self.animation_combo.setCurrentIndex(idx)
            if 'opacity' in config:
                self.opacity_spinbox.setValue(config['opacity'])
            if 'fill_color' in config:
                idx = self.fill_color_combo.findText(config['fill_color'])
                if idx >= 0:
                    self.fill_color_combo.setCurrentIndex(idx)
            if 'corner_radius' in config:
                self.corner_radius_spinbox.setValue(config['corner_radius'])
            if 'rect_margin' in config:
                self.rect_margin_spinbox.setValue(config['rect_margin'])
            if 'effect' in config:
                idx = self.effect_combo.findText(config['effect'])
                if idx >= 0:
                    self.effect_combo.setCurrentIndex(idx)
            
            # Cargar opción de nombre original
            if 'keep_original_name' in config:
                self.keep_original_name.setChecked(config['keep_original_name'])
            if 'disable_popups' in config:
                self.disable_popups.setChecked(config['disable_popups'])
            
            self.update_style_preview()
            
        except Exception as e:
            print(f'Error al cargar estilos: {e}')
    
    def save_styles_config(self):
        """Guarda la configuración de estilos"""
        app_dir = get_app_path()
        config_path = os.path.join(app_dir, 'styles_config.json')
        
        config = {
            'pattern': self.pattern_combo.currentText(),
            'custom_pattern': self.custom_pattern_input.text(),
            'rect_color': self.color_combo.currentText(),
            'line_width': self.line_width_spinbox.value(),
            'line_style': self.line_style_combo.currentText(),
            'blink_speed': self.blink_speed_combo.currentText(),
            'duration': self.duration_spinbox.value(),
            'fill_style': self.fill_combo.currentText(),
            'animation_type': self.animation_combo.currentText(),
            'opacity': self.opacity_spinbox.value(),
            'fill_color': self.fill_color_combo.currentText(),
            'corner_radius': self.corner_radius_spinbox.value(),
            'rect_margin': self.rect_margin_spinbox.value(),
            'effect': self.effect_combo.currentText(),
            'keep_original_name': self.keep_original_name.isChecked(),
            'disable_popups': self.disable_popups.isChecked()
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f'Error al guardar estilos: {e}')
    
    def on_pattern_changed(self, pattern_name):
        """Maneja el cambio de patrón seleccionado"""
        self.current_pattern = pattern_name
        
        if pattern_name == 'Personalizado':
            self.custom_pattern_input.setEnabled(True)
            self.pattern_example.setText('Escribe tu formato')
            self.pattern_hint.show()
            self.pattern_preview_label.show()
            # Actualizar preview si ya hay texto
            self.on_custom_pattern_changed(self.custom_pattern_input.text())
        else:
            self.custom_pattern_input.setEnabled(False)
            self.pattern_hint.hide()
            self.pattern_preview_label.hide()
            pattern_info = self.REFERENCE_PATTERNS.get(pattern_name, {})
            self.pattern_example.setText(pattern_info.get('example', ''))
        
        self.statusBar().showMessage(f'Patrón seleccionado: {pattern_name}')
    
    def on_custom_pattern_changed(self, text):
        """Maneja el cambio en el patrón personalizado y genera regex"""
        self.custom_pattern = text
        
        if text:
            # Convertir formato simple a regex y mostrar preview
            regex, example, valid = self.convert_simple_pattern_to_regex(text)
            if valid:
                self.pattern_preview_label.setText(f'✓ Detectará: {example}')
                self.pattern_preview_label.setStyleSheet('''
                    color: #10b981;
                    font-size: 11px;
                    padding: 2px 0;
                    margin-left: 55px;
                ''')
            else:
                self.pattern_preview_label.setText(f'⚠ Patrón: {regex}')
                self.pattern_preview_label.setStyleSheet('''
                    color: #f59e0b;
                    font-size: 11px;
                    padding: 2px 0;
                    margin-left: 55px;
                ''')
        else:
            self.pattern_preview_label.setText('')
    
    def convert_simple_pattern_to_regex(self, simple_pattern):
        """
        Convierte un patrón simple con placeholders a regex.
        
        Placeholders soportados:
        - {P} = Página (número)
        - {C} = Columna (número)  
        - {F} = Fila (letra A-Z)
        
        Ejemplo: /{P}.{C}-{F} → \/(\d+)\.(\d+)-([A-Z])
        """
        import re
        
        # Detectar si usa placeholders simples
        has_placeholders = any(p in simple_pattern.upper() for p in ['{P}', '{C}', '{F}', '{PAG}', '{COL}', '{FILA}'])
        
        if has_placeholders:
            # Convertir a regex
            regex = simple_pattern
            
            # Escapar caracteres especiales de regex primero (excepto los placeholders)
            special_chars = ['\\', '.', '^', '$', '*', '+', '?', '[', ']', '(', ')', '|']
            for char in special_chars:
                # No escapar si está dentro de un placeholder
                regex = regex.replace(char, '\\' + char)
            
            # Reemplazar placeholders por grupos de captura
            # Orden de grupos según aparición
            regex = re.sub(r'\{P\}|\{PAG\}|\{PAGINA\}', r'(\\d+)', regex, flags=re.IGNORECASE)
            regex = re.sub(r'\{C\}|\{COL\}|\{COLUMNA\}', r'(\\d+)', regex, flags=re.IGNORECASE)
            regex = re.sub(r'\{F\}|\{FILA\}', r'([A-Z])', regex, flags=re.IGNORECASE)
            
            # Generar ejemplo
            example = simple_pattern
            example = re.sub(r'\{P\}|\{PAG\}|\{PAGINA\}', '5', example, flags=re.IGNORECASE)
            example = re.sub(r'\{C\}|\{COL\}|\{COLUMNA\}', '3', example, flags=re.IGNORECASE)
            example = re.sub(r'\{F\}|\{FILA\}', 'A', example, flags=re.IGNORECASE)
            
            return regex, example, True
        else:
            # Asumir que es un regex directo
            return simple_pattern, simple_pattern, False
    
    def update_style_preview(self, color_name=None):
        """Actualiza el preview del estilo del rectángulo y guarda configuración"""
        if color_name is None:
            color_name = self.color_combo.currentText()
        
        colors = {
            'Rojo': '#ef4444',
            'Verde': '#22c55e',
            'Azul': '#3b82f6',
            'Amarillo': '#fbbf24',
            'Naranja': '#f97316',
            'Magenta': '#d946ef',
            'Cian': '#06b6d4'
        }
        color = colors.get(color_name, '#ef4444')
        self.style_preview.setStyleSheet(f'''
            color: {color};
            font-size: 20px;
            font-weight: bold;
            letter-spacing: 2px;
        ''')
        
        # Guardar configuración
        self.save_styles_config()
    
    def show_references_dialog(self):
        """Muestra ventana emergente con las referencias detectadas"""
        dialog = QDialog(self)
        dialog.setWindowTitle('📋 Referencias Detectadas')
        dialog.setMinimumSize(900, 600)
        dialog.setStyleSheet('''
            QDialog {
                background-color: #0f172a;
            }
        ''')
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QHBoxLayout()
        title = QLabel('📋 Referencias Detectadas')
        title.setStyleSheet('font-size: 20px; font-weight: bold; color: #f1f5f9;')
        header.addWidget(title)
        header.addStretch()
        
        count_label = QLabel(f'{len(self.references)} referencias')
        count_label.setStyleSheet('''
            color: #10b981;
            font-size: 14px;
            padding: 8px 15px;
            border: 1px solid #10b981;
            border-radius: 6px;
            font-weight: bold;
        ''')
        header.addWidget(count_label)
        layout.addLayout(header)
        
        # Tabla
        table = QTableWidget()
        if len(self.pdf_paths) > 1:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(['PDF', 'Referencia', 'Página', 'Columna', 'Fila', 'Contexto'])
        else:
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(['Referencia', 'Página', 'Columna', 'Fila', 'Contexto'])
        
        table.setRowCount(len(self.references))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(table.columnCount() - 1, QHeaderView.Stretch)
        table.setAlternatingRowColors(True)
        table.setStyleSheet('''
            QTableWidget {
                background-color: #1e293b;
                alternate-background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #e2e8f0;
            }
            QHeaderView::section {
                background-color: #334155;
                color: #f1f5f9;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        ''')
        
        for row, ref in enumerate(self.references):
            col_offset = 0
            if len(self.pdf_paths) > 1:
                pdf_name = ref.get('pdf_name', 'Unknown')
                if len(pdf_name) > 25:
                    pdf_name = pdf_name[:22] + '...'
                table.setItem(row, 0, QTableWidgetItem(pdf_name))
                col_offset = 1
            
            ref_text = ref['full']
            if ref.get('instance', 1) > 1:
                ref_text += f" (#{ref['instance']})"
            
            table.setItem(row, col_offset + 0, QTableWidgetItem(ref_text))
            table.setItem(row, col_offset + 1, QTableWidgetItem(ref['page']))
            table.setItem(row, col_offset + 2, QTableWidgetItem(ref['column']))
            table.setItem(row, col_offset + 3, QTableWidgetItem(ref['row']))
            
            context_text = ref['context']
            if ref.get('coordinates'):
                context_text += f" [Pág PDF: {ref['pdf_page']+1}]"
            table.setItem(row, col_offset + 4, QTableWidgetItem(context_text))
        
        layout.addWidget(table)
        
        # Botón cerrar
        close_btn = QPushButton('Cerrar')
        close_btn.clicked.connect(dialog.accept)
        close_btn.setStyleSheet('''
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 10px 30px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #60a5fa;
            }
        ''')
        layout.addWidget(close_btn, 0, Qt.AlignCenter)
        
        dialog.exec_()
    
    def show_statistics_dialog(self):
        """Muestra ventana emergente con las estadísticas"""
        dialog = QDialog(self)
        dialog.setWindowTitle('📊 Estadísticas')
        dialog.setMinimumSize(600, 500)
        dialog.setStyleSheet('''
            QDialog {
                background-color: #0f172a;
            }
        ''')
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        title = QLabel('📊 Estadísticas del Análisis')
        title.setStyleSheet('font-size: 20px; font-weight: bold; color: #f1f5f9;')
        layout.addWidget(title)
        
        # Contenido
        stats_display = QTextEdit()
        stats_display.setReadOnly(True)
        stats_display.setText(self.stats_text.toPlainText())
        stats_display.setStyleSheet('''
            QTextEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #e2e8f0;
                padding: 20px;
                font-size: 14px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        ''')
        layout.addWidget(stats_display)
        
        # Botón cerrar
        close_btn = QPushButton('Cerrar')
        close_btn.clicked.connect(dialog.accept)
        close_btn.setStyleSheet('''
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 10px 30px;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #60a5fa;
            }
        ''')
        layout.addWidget(close_btn, 0, Qt.AlignCenter)
        
        dialog.exec_()
    
    def get_highlight_color(self):
        """Obtiene el color de resaltado seleccionado para JavaScript"""
        color_map = {
            'Rojo': 'color.red',
            'Verde': 'color.green',
            'Azul': 'color.blue',
            'Amarillo': 'color.yellow',
            'Naranja': '["RGB", 0.976, 0.451, 0.086]',
            'Magenta': 'color.magenta',
            'Cian': 'color.cyan'
        }
        return color_map.get(self.color_combo.currentText(), 'color.red')
    
    def get_fill_color(self):
        """Obtiene el color de relleno seleccionado para JavaScript"""
        fill_color_name = self.fill_color_combo.currentText()
        
        if fill_color_name == 'Mismo que borde':
            return self.get_highlight_color()
        
        color_map = {
            'Rojo': 'color.red',
            'Verde': 'color.green',
            'Azul': 'color.blue',
            'Amarillo': 'color.yellow',
            'Naranja': '["RGB", 0.976, 0.451, 0.086]',
            'Magenta': 'color.magenta',
            'Cian': 'color.cyan',
            'Blanco': 'color.white',
            'Negro': 'color.black'
        }
        return color_map.get(fill_color_name, 'color.red')
    
    def get_blink_speed(self):
        """Obtiene la velocidad de parpadeo en milisegundos"""
        speed_map = {
            'Rápido': 300,
            'Normal': 500,
            'Lento': 800,
            'Sin parpadeo': 0
        }
        return speed_map.get(self.blink_speed_combo.currentText(), 500)
    
    def get_highlight_duration(self):
        """Obtiene la duración del resaltado en milisegundos"""
        return self.duration_spinbox.value() * 1000
    
    def update_rows_info(self, value):
        """Actualiza la información de filas según el valor del spinbox"""
        if value <= 26:
            last_letter = chr(ord('A') + value - 1)
            self.rows_info_label.setText(f'(A-{last_letter})')
        else:
            self.rows_info_label.setText(f'(A-Z + {value - 26})')
    
    def open_visual_editor(self):
        """
        Abre el editor visual para dibujar manualmente la cuadrícula.
        Permite al usuario hacer clic en el PDF para definir las líneas
        de columnas y filas de forma precisa.
        """
        if not self.pdf_path:
            QMessageBox.warning(self, 'Aviso', 'Primero debes seleccionar un archivo PDF.')
            return
        
        # Crear y mostrar el diálogo del editor
        dialog = GridEditorDialog(self, self.pdf_path)
        
        if dialog.exec_() == QDialog.Accepted:
            # Obtener los datos de la cuadrícula
            grid_data = dialog.get_grid_data()
            
            col_positions = grid_data['column_positions']
            row_positions = grid_data['row_positions']
            
            if len(col_positions) < 2:
                QMessageBox.warning(self, 'Aviso', 
                    'Debes definir al menos 2 líneas de columnas para crear cuadrantes.')
                return
            
            if len(row_positions) < 2:
                QMessageBox.warning(self, 'Aviso', 
                    'Debes definir al menos 2 líneas de filas para crear cuadrantes.')
                return
            
            # Guardar las posiciones para usarlas en el resaltado
            self.column_positions = col_positions
            self.row_positions = row_positions
            self.grid_detected = True
            
            # Calcular número de columnas y filas (cuadrantes = líneas - 1)
            num_cols = len(col_positions) - 1
            num_rows = len(row_positions) - 1
            
            # Actualizar la interfaz
            self.cols_spinbox.setValue(num_cols)
            self.rows_spinbox.setValue(num_rows)
            
            # Calcular márgenes aproximados
            page_width = grid_data['page_width']
            page_height = grid_data['page_height']
            
            if col_positions:
                margin_left_pct = int((col_positions[0] / page_width) * 100)
                self.margin_left_spinbox.setValue(max(0, min(margin_left_pct, 30)))
            
            if row_positions:
                margin_top_pct = int((row_positions[0] / page_height) * 100)
                self.margin_top_spinbox.setValue(max(0, min(margin_top_pct, 30)))
            
            # Calcular tamaños relativos de columnas
            col_widths = []
            for i in range(len(col_positions) - 1):
                col_widths.append(col_positions[i + 1] - col_positions[i])
            if col_widths:
                min_width = min(col_widths)
                if min_width > 0:
                    relative_cols = [round(w / min_width, 2) for w in col_widths]
                    self.col_sizes_input.setText(','.join(str(s) for s in relative_cols))
            
            # Calcular tamaños relativos de filas
            row_heights = []
            for i in range(len(row_positions) - 1):
                row_heights.append(row_positions[i + 1] - row_positions[i])
            if row_heights:
                min_height = min(row_heights)
                if min_height > 0:
                    relative_rows = [round(h / min_height, 2) for h in row_heights]
                    self.row_sizes_input.setText(','.join(str(s) for s in relative_rows))
            
            # Mostrar mensaje de éxito y actualizar indicador
            self.config_status.setText(f'● {num_cols}×{num_rows} cuadrantes')
            self.config_status.setStyleSheet('''
                color: #10b981;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
                padding: 4px 10px;
                border: 1px solid #10b981;
                border-radius: 4px;
            ''')
            
            QMessageBox.information(self, 'Cuadrícula Aplicada',
                f'✅ Cuadrícula configurada manualmente:\n\n'
                f'• Columnas: {num_cols}\n'
                f'• Filas: {num_rows}\n'
                f'• Posiciones exactas guardadas\n\n'
                f'El rectángulo de resaltado cubrirá exactamente cada cuadrante.')
    
    def autodetect_grid(self):
        """
        Analiza el PDF para detectar automáticamente la cuadrícula del esquema.
        Busca los números de columna (0, 1, 2...) y letras de fila (A, B, C...)
        en los bordes del cajetín del esquema eléctrico.
        """
        if not self.pdf_path:
            QMessageBox.warning(self, 'Aviso', 'Primero debes seleccionar un archivo PDF.')
            return
        
        self.statusBar().showMessage('Analizando cuadrícula del PDF...')
        
        try:
            # Abrir el PDF
            doc = fitz.open(self.pdf_path)
            
            if len(doc) == 0:
                QMessageBox.warning(self, 'Aviso', 'El PDF está vacío.')
                doc.close()
                return
            
            # Obtener el número de página seleccionado (convertir de 1-indexed a 0-indexed)
            selected_page = self.scan_page_spinbox.value() - 1
            
            # Verificar que la página existe
            if selected_page >= len(doc):
                QMessageBox.warning(self, 'Aviso', 
                    f'El PDF solo tiene {len(doc)} páginas.\n'
                    f'Seleccionaste la página {selected_page + 1}.')
                doc.close()
                return
            
            # Actualizar el máximo del spinbox con el número real de páginas
            self.scan_page_spinbox.setMaximum(len(doc))
            
            # Usar la página seleccionada para detectar la cuadrícula
            page = doc[selected_page]
            self.statusBar().showMessage(f'Analizando página {selected_page + 1} de {len(doc)}...')
            rect = page.rect
            width = rect.width
            height = rect.height
            
            # Listas para almacenar etiquetas de columnas y filas
            column_labels = []  # [(x_pos, num, texto), ...]  Números: 0, 1, 2, 3...
            row_labels = []     # [(y_pos, texto), ...]  Letras: A, B, C, D...
            
            # Debug: guardar todo el texto encontrado para análisis
            debug_all_text = []
            
            # Definir zonas de búsqueda (bordes del cajetín)
            # Basado en tu esquema: números MUY arriba, letras MUY a la derecha
            top_zone = height * 0.04      # 4% superior (primera línea donde están 0,1,2,3...)
            bottom_zone = height * 0.85   # 85% inferior (antes del cajetín de info)
            
            # Las letras de fila están en el extremo derecho
            right_zone = width * 0.96     # 96% derecho (donde están A,B,C...)
            left_zone = width * 0.04      # 4% izquierdo
            
            # Obtener TODAS las palabras del documento
            words = page.get_text("words")
            
            # Analizar cada palabra
            for word in words:
                x0, y0, x1, y1, text, *_ = word
                text = text.strip()
                
                if not text:
                    continue
                
                # Centro del texto
                x_center = (x0 + x1) / 2
                y_center = (y0 + y1) / 2
                
                # Guardar para debug
                debug_all_text.append({
                    'text': text,
                    'x': x_center,
                    'y': y_center,
                    'x_pct': (x_center / width) * 100,
                    'y_pct': (y_center / height) * 100
                })
                
                # COLUMNAS: Buscar números (0-9, 10, etc.) en zona SUPERIOR
                if text.isdigit():
                    num = int(text)
                    if num <= 15:  # Solo números razonables para columnas (0-15)
                        # Verificar si está en el borde superior (primeras líneas)
                        if y_center < top_zone:
                            column_labels.append((x_center, num, text))
                
                # FILAS: Buscar letras sueltas (A-Z) en zona DERECHA
                if len(text) == 1 and text.isalpha():
                    letter = text.upper()
                    if letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        # Verificar si está en el borde derecho
                        if x_center > right_zone:
                            row_labels.append((y_center, letter))
            
            # Si no encontramos columnas, buscar con zona más amplia
            if not column_labels:
                top_zone_expanded = height * 0.08  # Expandir a 8%
                for item in debug_all_text:
                    if item['text'].isdigit():
                        num = int(item['text'])
                        if num <= 15 and item['y'] < top_zone_expanded:
                            column_labels.append((item['x'], num, item['text']))
            
            # Si no encontramos filas, buscar con zona más amplia
            if not row_labels:
                right_zone_expanded = width * 0.92  # Expandir a 92%
                for item in debug_all_text:
                    if len(item['text']) == 1 and item['text'].isalpha():
                        letter = item['text'].upper()
                        if letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' and item['x'] > right_zone_expanded:
                            row_labels.append((item['y'], letter))
            
            # Guardar número de páginas antes de cerrar
            total_pages = len(doc)
            doc.close()
            
            # Procesar columnas: eliminar duplicados y ordenar
            # Agrupar por número de columna
            col_positions = {}
            for x, num, text in column_labels:
                if num not in col_positions:
                    col_positions[num] = []
                col_positions[num].append(x)
            
            # Calcular posición promedio de cada columna
            column_data = []
            for num, positions in col_positions.items():
                avg_x = sum(positions) / len(positions)
                column_data.append((avg_x, num))
            
            # Ordenar por posición X
            column_data.sort(key=lambda x: x[0])
            
            # Procesar filas: eliminar duplicados y ordenar
            row_positions = {}
            for y, letter in row_labels:
                if letter not in row_positions:
                    row_positions[letter] = []
                row_positions[letter].append(y)
            
            # Calcular posición promedio de cada fila
            row_data = []
            for letter, positions in row_positions.items():
                avg_y = sum(positions) / len(positions)
                row_data.append((avg_y, letter))
            
            # Ordenar por posición Y (de arriba a abajo)
            row_data.sort(key=lambda x: x[0])
            
            # Calcular número de columnas y filas
            num_cols = len(column_data) if column_data else 10
            num_rows = len(row_data) if row_data else 8
            
            # Calcular tamaños relativos de columnas
            col_sizes = []
            if len(column_data) >= 2:
                positions = [c[0] for c in column_data]
                # Añadir una posición final estimada
                if len(positions) >= 2:
                    avg_width = (positions[-1] - positions[0]) / (len(positions) - 1)
                    positions.append(positions[-1] + avg_width)
                col_sizes = self.calculate_relative_sizes(positions)
            
            # Calcular tamaños relativos de filas
            row_sizes = []
            if len(row_data) >= 2:
                positions = [r[0] for r in row_data]
                # Añadir una posición final estimada
                if len(positions) >= 2:
                    avg_height = (positions[-1] - positions[0]) / (len(positions) - 1)
                    positions.append(positions[-1] + avg_height)
                row_sizes = self.calculate_relative_sizes(positions)
            
            # Calcular márgenes
            margin_left_pct = 5
            margin_top_pct = 5
            
            if column_data:
                first_col_x = column_data[0][0]
                margin_left_pct = int((first_col_x / width) * 100)
                margin_left_pct = max(0, min(margin_left_pct - 2, 30))  # Ajustar un poco
            
            if row_data:
                first_row_y = row_data[0][0]
                margin_top_pct = int((first_row_y / height) * 100)
                margin_top_pct = max(0, min(margin_top_pct - 2, 30))  # Ajustar un poco
            
            # GUARDAR POSICIONES EXACTAS para usar en el rectángulo de resaltado
            # Posiciones de columnas (X de cada columna)
            if len(column_data) >= 2:
                self.column_positions = [c[0] for c in column_data]
                # Añadir posición final estimada
                avg_col_width = (self.column_positions[-1] - self.column_positions[0]) / (len(self.column_positions) - 1)
                self.column_positions.append(self.column_positions[-1] + avg_col_width)
            else:
                self.column_positions = []
            
            # Posiciones de filas (Y de cada fila)
            if len(row_data) >= 2:
                self.row_positions = [r[0] for r in row_data]
                # Añadir posición final estimada
                avg_row_height = (self.row_positions[-1] - self.row_positions[0]) / (len(self.row_positions) - 1)
                self.row_positions.append(self.row_positions[-1] + avg_row_height)
            else:
                self.row_positions = []
            
            # Marcar que se detectó la cuadrícula
            self.grid_detected = len(self.column_positions) > 1 and len(self.row_positions) > 1
            
            # Aplicar los valores detectados a la interfaz
            self.cols_spinbox.setValue(num_cols)
            self.rows_spinbox.setValue(num_rows)
            self.margin_left_spinbox.setValue(margin_left_pct)
            self.margin_top_spinbox.setValue(margin_top_pct)
            
            if col_sizes:
                self.col_sizes_input.setText(','.join([str(round(s, 2)) for s in col_sizes]))
            else:
                self.col_sizes_input.setText('')
            
            if row_sizes:
                self.row_sizes_input.setText(','.join([str(round(s, 2)) for s in row_sizes]))
            else:
                self.row_sizes_input.setText('')
            
            # Preparar información de columnas y filas detectadas
            cols_info = ', '.join([str(c[1]) for c in column_data]) if column_data else 'No detectadas'
            rows_info = ', '.join([r[1] for r in row_data]) if row_data else 'No detectadas'
            
            # Mostrar resumen
            msg = f"Cuadrícula detectada desde el cajetín:\n"
            msg += f"📄 Página escaneada: {selected_page + 1} de {total_pages}\n\n"
            msg += f"📊 Columnas encontradas: {cols_info}\n"
            msg += f"   Total: {num_cols} columnas\n\n"
            msg += f"📊 Filas encontradas: {rows_info}\n"
            msg += f"   Total: {num_rows} filas\n\n"
            msg += f"📐 Margen izquierdo: {margin_left_pct}%\n"
            msg += f"📐 Margen superior: {margin_top_pct}%\n\n"
            
            if not column_data and not row_data:
                msg += "⚠️ No se encontraron etiquetas de columnas ni filas.\n\n"
                msg += "📋 Debug - Texto en bordes (primeros 10):\n"
                border_texts = [t for t in debug_all_text if t['y_pct'] < 10 or t['x_pct'] > 90]
                for t in border_texts[:10]:
                    msg += f"   '{t['text']}' X:{t['x_pct']:.0f}% Y:{t['y_pct']:.0f}%\n"
                if not border_texts:
                    msg += "   (ningún texto en bordes)\n"
                msg += "\n💡 Ajusta manualmente: Columnas=10, Filas=6"
            elif not column_data:
                msg += "⚠️ No se encontraron números de columna.\n"
                msg += "   Zona búsqueda: Y < 4% superior\n"
            elif not row_data:
                msg += "⚠️ No se encontraron letras de fila.\n"
                msg += "   Zona búsqueda: X > 96% derecha\n"
            else:
                msg += "✅ Valores aplicados automáticamente.\n"
                msg += "✅ Se usarán los CUADRANTES EXACTOS para el resaltado.\n"
                msg += "\nEl rectángulo rojo cubrirá exactamente cada celda."
            
            QMessageBox.information(self, 'Detección de Cuadrícula', msg)
            self.statusBar().showMessage(f'Cuadrícula detectada: {num_cols} columnas, {num_rows} filas')
            
        except Exception as e:
            import traceback
            error_msg = f'Error al analizar la cuadrícula:\n{str(e)}\n\n{traceback.format_exc()}'
            QMessageBox.critical(self, 'Error', error_msg)
            self.statusBar().showMessage('Error al detectar cuadrícula')
    
    def filter_close_lines(self, lines, min_distance):
        """Filtra líneas que están muy cerca entre sí, manteniendo solo una"""
        if not lines:
            return []
        
        filtered = [lines[0]]
        for line in lines[1:]:
            if line - filtered[-1] >= min_distance:
                filtered.append(line)
        
        return filtered
    
    def calculate_relative_sizes(self, positions):
        """Calcula los tamaños relativos entre posiciones consecutivas"""
        if len(positions) < 2:
            return []
        
        # Calcular distancias entre posiciones consecutivas
        distances = []
        for i in range(1, len(positions)):
            distances.append(positions[i] - positions[i-1])
        
        if not distances:
            return []
        
        # Encontrar la distancia mínima para usar como unidad base
        min_dist = min(distances)
        if min_dist <= 0:
            return [1.0] * len(distances)
        
        # Calcular tamaños relativos
        relative_sizes = [d / min_dist for d in distances]
        
        return relative_sizes
    
    def update_size_placeholders(self):
        """Actualiza los placeholders de tamaños con el número correcto de elementos"""
        cols = self.cols_spinbox.value()
        rows = self.rows_spinbox.value()
        
        # Placeholder para columnas
        col_example = ','.join(['1'] * cols)
        self.col_sizes_input.setPlaceholderText(f'Ej: {col_example} (dejar vacío para iguales)')
        
        # Placeholder para filas
        row_example = ','.join(['1'] * rows)
        self.row_sizes_input.setPlaceholderText(f'Ej: {row_example} (dejar vacío para iguales)')
    
    def parse_sizes(self, sizes_text, count):
        """Parsea los tamaños desde el texto y devuelve una lista de proporciones"""
        if not sizes_text.strip():
            # Si está vacío, todos iguales
            return [1.0] * count
        
        try:
            sizes = [float(s.strip()) for s in sizes_text.split(',') if s.strip()]
            
            # Si hay menos valores que elementos, rellenar con 1
            while len(sizes) < count:
                sizes.append(1.0)
            
            # Si hay más valores, truncar
            sizes = sizes[:count]
            
            return sizes
        except ValueError:
            # Si hay error, todos iguales
            return [1.0] * count
    
    def calculate_position_with_sizes(self, index, sizes, total_size, margin_start):
        """
        Calcula la posición central de un elemento dado sus tamaños variables.
        
        Args:
            index: Índice del elemento (0, 1, 2, ...)
            sizes: Lista de tamaños relativos de cada elemento
            total_size: Tamaño total disponible (ancho o alto útil)
            margin_start: Margen inicial (izquierdo o superior)
        
        Returns:
            Posición central del elemento
        """
        # Calcular el tamaño total de las proporciones
        total_proportion = sum(sizes)
        
        # Tamaño de una unidad de proporción
        unit_size = total_size / total_proportion
        
        # Calcular la posición inicial del elemento
        position = margin_start
        for i in range(index):
            position += sizes[i] * unit_size
        
        # Calcular el centro del elemento
        element_size = sizes[index] * unit_size
        center = position + (element_size / 2)
        
        return center
    
    def show_pattern_help(self):
        """Muestra ayuda sobre los patrones de búsqueda"""
        help_text = """
<h3>Ayuda - Patrones de Referencias</h3>

<h4>Patrones Predefinidos:</h4>

<p><b>Estilo /1.0-A</b><br>
Formato: /página.columna-fila<br>
Ejemplos: /1.0-A, /10.5-Z, /3.12-AB</p>

<p><b>Estilo 25-A.0</b><br>
Formato: página-fila.columna<br>
Ejemplos: 25-A.0, 10-B.5, 3-C.12</p>

<p><b>Estilo A1/25</b><br>
Formato: fila+columna/página<br>
Ejemplos: A1/25, B5/10, C12/3</p>

<p><b>Estilo (1-A-0)</b><br>
Formato: (página-fila-columna)<br>
Ejemplos: (1-A-0), (10-B-5), (3-C-12)</p>

<hr>

<h4>🆕 Patrón Personalizado (Fácil):</h4>
<p>Escribe cómo se ve tu referencia usando estos <b>placeholders</b>:</p>

<table border="1" cellpadding="5" style="border-collapse: collapse;">
<tr style="background-color: #334155;">
    <th>Placeholder</th>
    <th>Significa</th>
    <th>Detecta</th>
</tr>
<tr>
    <td><code>{P}</code></td>
    <td>Página</td>
    <td>Números (1, 25, 100...)</td>
</tr>
<tr>
    <td><code>{C}</code></td>
    <td>Columna</td>
    <td>Números (0, 5, 12...)</td>
</tr>
<tr>
    <td><code>{F}</code></td>
    <td>Fila</td>
    <td>Letras (A, B, Z...)</td>
</tr>
</table>

<h4>Ejemplos de uso:</h4>
<table border="1" cellpadding="5" style="border-collapse: collapse;">
<tr style="background-color: #334155;">
    <th>Escribes</th>
    <th>Detectará</th>
</tr>
<tr>
    <td><code>/{P}.{C}-{F}</code></td>
    <td>/5.3-A, /10.0-B...</td>
</tr>
<tr>
    <td><code>{P}-{F}.{C}</code></td>
    <td>25-A.0, 10-B.5...</td>
</tr>
<tr>
    <td><code>[{P}/{F}/{C}]</code></td>
    <td>[5/A/3], [10/B/0]...</td>
</tr>
<tr>
    <td><code>REF:{P}-{C}{F}</code></td>
    <td>REF:5-3A, REF:10-0B...</td>
</tr>
<tr>
    <td><code>Pag{P} Col{C} Fila{F}</code></td>
    <td>Pag5 Col3 FilaA...</td>
</tr>
</table>

<p><b>💡 Tip:</b> También puedes usar <code>{PAG}</code>, <code>{COL}</code>, <code>{FILA}</code> si prefieres nombres más largos.</p>

<hr>
<p><i>Si necesitas regex avanzado, también puedes escribirlo directamente (sin placeholders).</i></p>
"""
        msg = QMessageBox(self)
        msg.setWindowTitle('Ayuda - Patrones de Referencias')
        msg.setTextFormat(Qt.RichText)
        msg.setText(help_text)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()
    
    def get_current_pattern(self):
        """Obtiene el patrón regex actual según la selección"""
        if self.current_pattern == 'Personalizado':
            if not self.custom_pattern:
                return None
            # Convertir patrón simple a regex si usa placeholders
            regex, _, has_placeholders = self.convert_simple_pattern_to_regex(self.custom_pattern)
            return regex
        else:
            return self.REFERENCE_PATTERNS.get(self.current_pattern, {}).get('pattern', '')
    
    def get_pattern_groups_order(self):
        """Obtiene el orden de los grupos según el patrón seleccionado"""
        if self.current_pattern == 'Personalizado' and self.custom_pattern:
            # Determinar orden de grupos basándose en la posición de los placeholders
            import re
            pattern_upper = self.custom_pattern.upper()
            
            # Encontrar posiciones de cada placeholder
            groups = []
            
            # Buscar todas las ocurrencias de placeholders
            p_match = re.search(r'\{P\}|\{PAG\}|\{PAGINA\}', pattern_upper)
            c_match = re.search(r'\{C\}|\{COL\}|\{COLUMNA\}', pattern_upper)
            f_match = re.search(r'\{F\}|\{FILA\}', pattern_upper)
            
            # Ordenar por posición
            placeholders = []
            if p_match:
                placeholders.append((p_match.start(), 'página'))
            if c_match:
                placeholders.append((c_match.start(), 'columna'))
            if f_match:
                placeholders.append((f_match.start(), 'fila'))
            
            placeholders.sort(key=lambda x: x[0])
            groups = tuple(p[1] for p in placeholders)
            
            return groups if groups else ('página', 'columna', 'fila')
        else:
            pattern_info = self.REFERENCE_PATTERNS.get(self.current_pattern, {})
            return pattern_info.get('groups', ('página', 'columna', 'fila'))
            
    def detect_references(self):
        """Detecta todas las referencias en todos los PDFs"""
        if not self.pdf_paths:
            QMessageBox.warning(self, 'Aviso', 'No hay PDFs cargados.')
            return
        
        # Obtener el patrón actual
        pattern = self.get_current_pattern()
        if not pattern:
            QMessageBox.warning(self, 'Aviso', 'Por favor, introduce un patrón regex válido.')
            return
        
        # Validar el patrón regex
        try:
            re.compile(pattern)
        except re.error as e:
            QMessageBox.critical(self, 'Error', f'Patrón regex inválido:\n{str(e)}')
            return
        
        # Calcular el total de páginas de todos los PDFs para la barra de progreso
        total_pages = 0
        pdf_page_counts = {}
        for pdf_path in self.pdf_paths:
            try:
                temp_doc = fitz.open(pdf_path)
                pdf_page_counts[pdf_path] = len(temp_doc)
                total_pages += len(temp_doc)
                temp_doc.close()
            except Exception:
                pdf_page_counts[pdf_path] = 0
        
        # Diálogo de progreso con total de páginas
        progress = QProgressDialog('Iniciando análisis...', 'Cancelar', 0, total_pages, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle('Detectando Referencias')
        progress.setMinimumDuration(0)  # Mostrar inmediatamente
        progress.setMinimumWidth(400)
        progress.setValue(0)
        
        # Forzar que se muestre la ventana
        QApplication.processEvents()
        
        self.table.setRowCount(0)
        self.references = []
        self.all_references = {}
        
        # Obtener el orden de los grupos
        groups_order = self.get_pattern_groups_order()
        
        total_references_all = 0
        pages_processed = 0
        
        try:
            # Procesar cada PDF
            for pdf_idx, pdf_path in enumerate(self.pdf_paths):
                if progress.wasCanceled():
                    break
                
                pdf_name = os.path.basename(pdf_path)
                
                # Cerrar documento previo si existe
                if self.pdf_document:
                    self.pdf_document.close()
                
                # Abrir el PDF con PyMuPDF
                try:
                    self.pdf_document = fitz.open(pdf_path)
                    self.pdf_path = pdf_path
                except Exception as e:
                    print(f"Error al abrir {pdf_path}: {e}")
                    continue
                
                pdf_references = []
                total_references = 0
                num_pages = len(self.pdf_document)
                
                # Recorrer todas las páginas
                for page_num in range(num_pages):
                    if progress.wasCanceled():
                        break
                    
                    # Actualizar barra de progreso con información detallada
                    pages_processed += 1
                    progress.setValue(pages_processed)
                    progress.setLabelText(
                        f'📄 {pdf_name}\n'
                        f'Página {page_num + 1}/{num_pages} • '
                        f'{total_references_all + total_references} referencias encontradas'
                    )
                    QApplication.processEvents()  # Actualizar UI
                    
                    try:
                        page = self.pdf_document[page_num]
                        text = page.get_text()
                        
                        # Buscar todas las coincidencias en la página usando regex
                        matches = list(re.finditer(pattern, text))
                        
                        # Para cada referencia única, encontrar TODAS sus posiciones en la página
                        ref_positions_used = {}
                        
                        for match in matches:
                            full_ref = match.group(0)
                            
                            # Extraer los grupos según el orden del patrón
                            group1 = match.group(1) if match.lastindex >= 1 else ''
                            group2 = match.group(2) if match.lastindex >= 2 else ''
                            group3 = match.group(3) if match.lastindex >= 3 else ''
                            
                            # Asignar página, columna y fila según el orden del patrón
                            page_ref, column_ref, row_ref = '', '', ''
                            
                            for i, group_name in enumerate(groups_order):
                                value = [group1, group2, group3][i] if i < 3 else ''
                                if group_name == 'página':
                                    page_ref = value
                                elif group_name == 'columna':
                                    column_ref = value
                                elif group_name == 'fila':
                                    row_ref = value
                            
                            # Obtener contexto (30 caracteres antes y después)
                            start = max(0, match.start() - 30)
                            end = min(len(text), match.end() + 30)
                            context = text[start:end].replace('\n', ' ').strip()
                            
                            # Buscar TODAS las coordenadas de esta referencia en la página
                            text_instances = page.search_for(full_ref)
                            
                            if text_instances:
                                # Inicializar contador para esta referencia si no existe
                                if full_ref not in ref_positions_used:
                                    ref_positions_used[full_ref] = 0
                                
                                # Obtener el índice de la posición que corresponde a este match
                                position_index = ref_positions_used[full_ref]
                                
                                # Si hay suficientes instancias, usar la que corresponde
                                if position_index < len(text_instances):
                                    rect = text_instances[position_index]
                                    coordinates = [rect.x0, rect.y0, rect.x1, rect.y1]
                                    
                                    reference_data = {
                                        'full': full_ref,
                                        'page': page_ref,
                                        'column': column_ref,
                                        'row': row_ref,
                                        'context': context,
                                        'pdf_page': page_num,
                                        'coordinates': coordinates,
                                        'instance': position_index + 1,
                                        'pdf_path': pdf_path,
                                        'pdf_name': os.path.basename(pdf_path)
                                    }
                                    
                                    pdf_references.append(reference_data)
                                    self.references.append(reference_data)
                                    total_references += 1
                                    
                                    # Incrementar el contador para la próxima vez
                                    ref_positions_used[full_ref] += 1
                                else:
                                    # Si no hay más instancias, usar la última disponible
                                    rect = text_instances[-1]
                                    coordinates = [rect.x0, rect.y0, rect.x1, rect.y1]
                                    
                                    reference_data = {
                                        'full': full_ref,
                                        'page': page_ref,
                                        'column': column_ref,
                                        'row': row_ref,
                                        'context': context,
                                        'pdf_page': page_num,
                                        'coordinates': coordinates,
                                        'instance': len(text_instances),
                                        'pdf_path': pdf_path,
                                        'pdf_name': os.path.basename(pdf_path)
                                    }
                                    
                                    pdf_references.append(reference_data)
                                    self.references.append(reference_data)
                                    total_references += 1
                    except Exception as page_error:
                        # Si hay error en una página, continuar con las demás
                        print(f"Error procesando página {page_num + 1} de {pdf_name}: {page_error}")
                        continue
                
                # Guardar referencias de este PDF
                self.all_references[pdf_path] = pdf_references
                total_references_all += total_references
            
            # Completar la barra de progreso
            progress.setValue(total_pages)
            progress.setLabelText(f'✅ Análisis completado: {total_references_all} referencias')
            QApplication.processEvents()
            
            # Mostrar referencias en la tabla
            self.populate_table()
            
            # Actualizar estadísticas
            self.update_statistics(total_references_all)
            
            # Habilitar el botón de generar PDF interactivo
            if total_references_all > 0:
                self.generate_button.setEnabled(True)
            
            self.statusBar().showMessage(f'✅ Análisis completado: {total_references_all} referencias en {len(self.pdf_paths)} PDF(s)')
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"Error en detección: {error_detail}")
            QMessageBox.critical(self, 'Error', f'Error al procesar el PDF:\n{str(e)}')
            self.statusBar().showMessage('Error al analizar el PDF')
            
    def populate_table(self):
        """Llena la tabla con las referencias encontradas"""
        # Actualizar columnas si hay múltiples PDFs
        if len(self.pdf_paths) > 1:
            self.table.setColumnCount(6)
            self.table.setHorizontalHeaderLabels(['PDF', 'Referencia', 'Página', 'Columna', 'Fila', 'Contexto'])
            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        else:
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels(['Referencia', 'Página', 'Columna', 'Fila', 'Contexto'])
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        
        self.table.setRowCount(len(self.references))
        
        for row, ref in enumerate(self.references):
            col_offset = 0
            
            # Mostrar nombre del PDF si hay múltiples
            if len(self.pdf_paths) > 1:
                pdf_name = ref.get('pdf_name', 'Unknown')
                # Acortar el nombre si es muy largo
                if len(pdf_name) > 25:
                    pdf_name = pdf_name[:22] + '...'
                self.table.setItem(row, 0, QTableWidgetItem(pdf_name))
                col_offset = 1
            
            # Mostrar referencia con número de instancia si hay duplicados
            ref_text = ref['full']
            if ref.get('instance', 1) > 1:
                ref_text += f" (#{ref['instance']})"
            
            self.table.setItem(row, col_offset + 0, QTableWidgetItem(ref_text))
            self.table.setItem(row, col_offset + 1, QTableWidgetItem(ref['page']))
            self.table.setItem(row, col_offset + 2, QTableWidgetItem(ref['column']))
            self.table.setItem(row, col_offset + 3, QTableWidgetItem(ref['row']))
            
            # Añadir información de coordenadas al contexto si están disponibles
            context_text = ref['context']
            if ref.get('coordinates'):
                context_text += f" [Pág PDF: {ref['pdf_page']+1}]"
            
            self.table.setItem(row, col_offset + 4, QTableWidgetItem(context_text))
            
    def update_statistics(self, total):
        """Actualiza el área de estadísticas"""
        pattern_info = self.REFERENCE_PATTERNS.get(self.current_pattern, {})
        pattern_order = pattern_info.get('order', 'desconocido')
        pattern_example = pattern_info.get('example', '')
        
        if total == 0:
            stats = f"""
Estilo de referencia: {self.current_pattern}
Formato: {pattern_order}
Ejemplo: {pattern_example}

No se encontraron referencias en el documento.
            """
        else:
            # Contar referencias únicas
            unique_refs = len(set(ref['full'] for ref in self.references))
            pages_with_refs = len(set(ref['page'] for ref in self.references))
            
            stats = f"""
Estilo de referencia: {self.current_pattern}
Formato: {pattern_order}
Ejemplo: {pattern_example}

ESTADÍSTICAS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total de referencias encontradas: {total}
Referencias únicas: {unique_refs}
Páginas referenciadas: {pages_with_refs}

Distribución por página:
"""
            # Contar por página
            page_counts = {}
            for ref in self.references:
                page = ref['page']
                page_counts[page] = page_counts.get(page, 0) + 1
            
            for page in sorted(page_counts.keys(), key=lambda x: int(x) if x.isdigit() else 0):
                stats += f"  Página {page}: {page_counts[page]} referencias\n"
                
        self.stats_text.setText(stats.strip())
        
        # Actualizar contador de referencias en la pestaña
        total_refs = len(self.references)
        if total_refs == 0:
            self.ref_count_label.setText('No se encontraron referencias')
            self.ref_count_label.setStyleSheet('color: #f87171; font-size: 12px; padding: 5px;')
        elif total_refs == 1:
            self.ref_count_label.setText('1 referencia encontrada')
            self.ref_count_label.setStyleSheet('color: #10b981; font-size: 12px; padding: 5px;')
        else:
            self.ref_count_label.setText(f'{total_refs} referencias encontradas')
            self.ref_count_label.setStyleSheet('color: #10b981; font-size: 12px; padding: 5px;')
        
        # Mostrar diálogo de referencias automáticamente
        if total_refs > 0:
            self.show_references_dialog()
    
    def generate_interactive_pdf(self):
        """Genera PDFs interactivos para todos los archivos cargados"""
        if not self.all_references:
            QMessageBox.warning(self, 'Aviso', 'Primero debes detectar las referencias.')
            return
        
        keep_name = self.keep_original_name.isChecked()
        
        # Si se mantiene el nombre original, avisar de sobrescritura
        if keep_name:
            reply = QMessageBox.question(
                self, 
                'Confirmar sobrescritura',
                f'Se sobrescribirán {len(self.pdf_paths)} archivo(s) original(es).\n\n¿Continuar?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            output_dir = None
            single_output = None
        else:
            # Pedir al usuario dónde guardar los PDFs
            if len(self.pdf_paths) == 1:
                # Un solo PDF: pedir nombre de archivo
                output_path, _ = QFileDialog.getSaveFileName(
                    self,
                    'Guardar PDF Interactivo',
                    self.pdf_paths[0].replace('.pdf', '_interactivo.pdf'),
                    'Archivos PDF (*.pdf)'
                )
                if not output_path:
                    return
                output_dir = os.path.dirname(output_path)
                single_output = output_path
            else:
                # Múltiples PDFs: pedir carpeta de destino
                output_dir = QFileDialog.getExistingDirectory(
                    self,
                    'Seleccionar carpeta para guardar los PDFs interactivos',
                    os.path.dirname(self.pdf_paths[0])
                )
                if not output_dir:
                    return
                single_output = None
        
        try:
            total_pdfs = len(self.all_references)
            total_refs_processed = 0
            pdfs_generated = []
            
            # Crear un diálogo de progreso
            progress = QProgressDialog(f'Generando {total_pdfs} PDF(s) interactivo(s)...', 'Cancelar', 0, total_pdfs, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle('Procesando PDFs')
            progress.setValue(0)
            
            # Procesar cada PDF
            for pdf_idx, (pdf_path, pdf_refs) in enumerate(self.all_references.items()):
                if progress.wasCanceled():
                    break
                
                progress.setLabelText(f'Procesando: {os.path.basename(pdf_path)}')
                progress.setValue(pdf_idx)
                
                if not pdf_refs:
                    continue
                
                try:
                    # Determinar ruta de salida
                    if keep_name:
                        # Usar archivo temporal y luego reemplazar
                        current_output = pdf_path + '.tmp'
                        final_output = pdf_path
                    elif single_output and pdf_idx == 0:
                        current_output = single_output
                        final_output = single_output
                    else:
                        base_name = os.path.basename(pdf_path).replace('.pdf', '_interactivo.pdf')
                        current_output = os.path.join(output_dir, base_name)
                        final_output = current_output
                    
                    # Contador de enlaces añadidos
                    links_added = 0
                    references_data = []
                    
                    # Abrir con PyMuPDF solo para obtener dimensiones de página
                    temp_doc = fitz.open(pdf_path)
                    
                    # Procesar cada referencia para calcular coordenadas
                    for idx, ref in enumerate(pdf_refs):
                        # Verificar que tenemos coordenadas
                        if not ref['coordinates']:
                            continue
                        
                        # Página donde está la referencia (0-indexed)
                        source_page_num = ref['pdf_page']
                        source_page = temp_doc[source_page_num]
                        
                        # Coordenadas de la referencia en el PDF actual
                        x0, y0, x1, y1 = ref['coordinates']
                        
                        # Convertir coordenadas de PyMuPDF a coordenadas PDF estándar
                        page_height = source_page.rect.height
                        pdf_y0 = page_height - y1
                        pdf_y1 = page_height - y0
                        
                        # Página destino (donde debe ir al hacer clic)
                        target_page_num = int(ref['page']) - 1
                        
                        # Verificar que la página destino existe
                        if target_page_num < 0 or target_page_num >= len(temp_doc):
                            continue
                        
                        # Obtener las coordenadas de destino basadas en columna y fila
                        target_coords = self.calculate_target_coordinates(
                            temp_doc[target_page_num],
                            ref['column'],
                            ref['row']
                        )
                        
                        # Convertir coordenadas de destino también
                        target_page_height = temp_doc[target_page_num].rect.height
                        target_pdf_coords = [
                            target_coords[0],
                            target_page_height - target_coords[3],
                            target_coords[2],
                            target_page_height - target_coords[1]
                        ]
                        
                        # Guardar datos de la referencia
                        ref_data = {
                            'full': ref['full'],
                            'page': ref['page'],
                            'column': ref['column'],
                            'row': ref['row'],
                            'pdf_page': source_page_num,
                            'coordinates': [x0, pdf_y0, x1, pdf_y1],
                            'target_page': target_page_num,
                            'target_coordinates': target_pdf_coords
                        }
                        references_data.append(ref_data)
                        links_added += 1
                    
                    temp_doc.close()
                    
                    # Usar PyPDF2 para crear el PDF con JavaScript
                    reader = PdfReader(pdf_path)
                    writer = PdfWriter()
                    
                    # Copiar todas las páginas manteniendo todo el contenido original
                    for page in reader.pages:
                        writer.add_page(page)
                    
                    # Añadir JavaScript a nivel de documento con los estilos configurados
                    writer.add_js(self.get_javascript_code())
                    
                    # Añadir nuevos enlaces invisibles con JavaScript Y GoTo para cada referencia
                    for ref_data in references_data:
                        try:
                            page_num = ref_data['pdf_page']
                            coords = ref_data['coordinates']
                            target_page = ref_data['target_page']
                            target_coords = ref_data['target_coordinates']
                            
                            # Obtener la página del writer
                            page = writer.pages[page_num]
                            
                            # JavaScript: solo ejecutar highlight (la navegación la hace GoTo)
                            js_code = f"highlight({target_page}, {target_coords});"
                            
                            # Crear acción JavaScript
                            js_action = DictionaryObject({
                                NameObject("/S"): NameObject("/JavaScript"),
                                NameObject("/JS"): createStringObject(js_code)
                            })
                            
                            # Crear acción GoTo para ir a la página destino
                            goto_action = DictionaryObject({
                                NameObject("/S"): NameObject("/GoTo"),
                                NameObject("/D"): ArrayObject([
                                    writer.pages[target_page].indirect_reference,
                                    NameObject("/XYZ"),
                                    NumberObject(int(target_coords[0])),
                                    NumberObject(int(target_coords[3])),
                                    NumberObject(0)
                                ])
                            })
                            
                            # Encadenar acciones: GoTo primero, luego JavaScript
                            goto_action[NameObject("/Next")] = js_action
                            
                            # Crear enlace invisible con acción combinada
                            link_annotation = DictionaryObject()
                            link_annotation.update({
                                NameObject("/Type"): NameObject("/Annot"),
                                NameObject("/Subtype"): NameObject("/Link"),
                                NameObject("/Rect"): ArrayObject([
                                    NumberObject(coords[0]),
                                    NumberObject(coords[1]),
                                    NumberObject(coords[2]),
                                    NumberObject(coords[3])
                                ]),
                                NameObject("/Border"): ArrayObject([
                                    NumberObject(0), NumberObject(0), NumberObject(0)
                                ]),
                                NameObject("/A"): goto_action,
                                NameObject("/H"): NameObject("/N")
                            })
                            
                            # Añadir la anotación a la página
                            if "/Annots" in page:
                                page["/Annots"].append(link_annotation)
                            else:
                                page[NameObject("/Annots")] = ArrayObject([link_annotation])
                            
                        except Exception as ref_error:
                            print(f"Error procesando referencia {ref_data.get('full', 'unknown')}: {ref_error}")
                            continue
                    
                    # Guardar el PDF final
                    with open(current_output, 'wb') as f:
                        writer.write(f)
                    
                    # Si estamos sobrescribiendo, reemplazar el archivo original
                    if keep_name and current_output != final_output:
                        import shutil
                        shutil.move(current_output, final_output)
                    
                    pdfs_generated.append(final_output)
                    total_refs_processed += links_added
                    
                except Exception as pdf_error:
                    import traceback
                    error_detail = traceback.format_exc()
                    print(f"Error al procesar {pdf_path}: {pdf_error}\n{error_detail}")
                    continue
            
            progress.setValue(total_pdfs)
            
            # Mensaje de resumen
            if len(pdfs_generated) == 1:
                msg = f'PDF interactivo generado correctamente! ✅\n\n'
                msg += f'📄 Archivo: {pdfs_generated[0]}\n'
                msg += f'🔗 Referencias procesadas: {total_refs_processed}\n\n'
            else:
                msg = f'{len(pdfs_generated)} PDFs interactivos generados! ✅\n\n'
                msg += f'📁 Carpeta: {output_dir}\n'
                msg += f'🔗 Total referencias: {total_refs_processed}\n\n'
                msg += 'Archivos generados:\n'
                for p in pdfs_generated[:5]:  # Mostrar máximo 5
                    msg += f'  • {os.path.basename(p)}\n'
                if len(pdfs_generated) > 5:
                    msg += f'  ... y {len(pdfs_generated) - 5} más\n'
                msg += '\n'
            
            msg += f'✨ Características:\n'
            msg += f'  • Acción "Ir a página" (funciona en todos los visores) ✓\n'
            msg += f'  • Animación JavaScript (Adobe Acrobat/Reader) ✓'
            
            # Mostrar mensaje solo si no están desactivadas las ventanas emergentes
            if not self.disable_popups.isChecked():
                QMessageBox.information(self, 'Éxito', msg)
            
            self.statusBar().showMessage(f'{len(pdfs_generated)} PDF(s) interactivo(s) generado(s) ✅')
            
        except Exception as e:
            import traceback
            error_msg = f'Error al generar PDF interactivo:\n{str(e)}\n\n{traceback.format_exc()}'
            QMessageBox.critical(self, 'Error', error_msg)
            self.statusBar().showMessage('Error al generar PDF interactivo')
    
    def coords_match(self, coords1, coords2, tolerance=5):
        """
        Compara dos conjuntos de coordenadas con una tolerancia
        para determinar si corresponden al mismo elemento
        """
        if not coords1 or not coords2:
            return False
        
        for i in range(4):
            if abs(coords1[i] - coords2[i]) > tolerance:
                return False
        return True
    
    def calculate_target_coordinates(self, target_page, column, row):
        """
        Calcula las coordenadas del cuadrante (celda) en la página destino.
        
        Si se detectó la cuadrícula del cajetín, usa las posiciones EXACTAS
        para crear un rectángulo que cubra todo el cuadrante.
        
        Si no, usa el cálculo basado en márgenes y tamaños configurados.
        """
        # Obtener dimensiones de la página
        rect = target_page.rect
        width = rect.width
        height = rect.height
        
        # Intentar convertir columna a número
        try:
            col_num = int(column)
        except ValueError:
            if column and column.isalpha():
                col_num = ord(column.upper()) - ord('A')
            else:
                col_num = 0
        
        # Calcular índice de fila (A=0, B=1, C=2, etc.)
        row_index = 0
        if row:
            if row.isalpha():
                if len(row) == 1:
                    row_index = ord(row.upper()) - ord('A')
                else:
                    for i, char in enumerate(row.upper()):
                        row_index += (ord(char) - ord('A') + 1) * (26 ** (len(row) - i - 1))
            elif row.isdigit():
                row_index = int(row)
        
        # MÉTODO 1: Si se detectó la cuadrícula del cajetín, usar posiciones EXACTAS
        if self.grid_detected and self.column_positions and self.row_positions:
            # Asegurar que los índices estén dentro del rango
            col_num = max(0, min(col_num, len(self.column_positions) - 2))
            row_index = max(0, min(row_index, len(self.row_positions) - 2))
            
            # Obtener las coordenadas exactas del cuadrante
            x0 = self.column_positions[col_num]
            x1 = self.column_positions[col_num + 1] if col_num + 1 < len(self.column_positions) else x0 + 50
            
            y0 = self.row_positions[row_index]
            y1 = self.row_positions[row_index + 1] if row_index + 1 < len(self.row_positions) else y0 + 50
            
            # Asegurar que las coordenadas estén dentro de la página
            x0 = max(0, min(x0, width))
            x1 = max(0, min(x1, width))
            y0 = max(0, min(y0, height))
            y1 = max(0, min(y1, height))
            
            return [x0, y0, x1, y1]
        
        # MÉTODO 2: Cálculo basado en configuración manual (fallback)
        margin_left_pct = self.margin_left_spinbox.value() / 100.0
        margin_top_pct = self.margin_top_spinbox.value() / 100.0
        
        margin_left = width * margin_left_pct
        margin_right = width * margin_left_pct
        margin_top = height * margin_top_pct
        margin_bottom = height * margin_top_pct
        
        usable_width = width - margin_left - margin_right
        usable_height = height - margin_top - margin_bottom
        
        cols_per_page = self.cols_spinbox.value()
        rows_per_page = self.rows_spinbox.value()
        
        col_sizes = self.parse_sizes(self.col_sizes_input.text(), cols_per_page)
        row_sizes = self.parse_sizes(self.row_sizes_input.text(), rows_per_page)
        
        col_num = max(0, min(col_num, cols_per_page - 1))
        row_index = max(0, min(row_index, rows_per_page - 1))
        
        # Calcular posiciones usando tamaños variables
        total_col_proportion = sum(col_sizes)
        total_row_proportion = sum(row_sizes)
        
        col_unit = usable_width / total_col_proportion
        row_unit = usable_height / total_row_proportion
        
        # Calcular X0 y X1 del cuadrante
        x0 = margin_left
        for i in range(col_num):
            x0 += col_sizes[i] * col_unit
        x1 = x0 + col_sizes[col_num] * col_unit
        
        # Calcular Y0 y Y1 del cuadrante
        y0 = margin_top
        for i in range(row_index):
            y0 += row_sizes[i] * row_unit
        y1 = y0 + row_sizes[row_index] * row_unit
        
        # Asegurar límites
        x0 = max(0, min(x0, width))
        x1 = max(0, min(x1, width))
        y0 = max(0, min(y0, height))
        y1 = max(0, min(y1, height))
        
        return [x0, y0, x1, y1]


def main():
    app = QApplication(sys.argv)
    
    # Establecer icono de la aplicación (para la barra de tareas)
    icon_path = os.path.join(get_app_path(), 'logo.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = PDFReferenceDetector()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

