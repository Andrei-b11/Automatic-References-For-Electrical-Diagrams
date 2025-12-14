# PDF Reference Detector

A powerful Python application built with PyQt5 for detecting and converting electrical schematic references in PDF documents into interactive clickable links with JavaScript highlighting.

## 🎯 Features

### Core Functionality
- **Reference Detection**: Automatically detects references in multiple formats (e.g., `/1.0-A`, `25-A.0`, `A1/25`)
- **Interactive PDF Generation**: Converts detected references into clickable links that highlight target locations
- **Visual Grid Editor**: Visual tool to manually define column and row positions for accurate coordinate calculation
- **Multiple Pattern Support**: Supports various reference formats with customizable regex patterns
- **Batch Processing**: Process multiple PDF files simultaneously
- **JSON Export**: Exports detected references with coordinates to JSON format

### Advanced Features
- **Customizable Highlighting**: 
  - Adjustable colors, line width, and style
  - Multiple animation types (Blink, Pulse, Fade In/Out)
  - Configurable duration and blink speed
  - Fill styles (Solid, Semi-transparent, None)
- **Grid Auto-detection**: Automatically detects grid positions from PDF content
- **Visual Preview**: Preview styling options before generating the PDF
- **Statistics Dashboard**: View detailed statistics about detected references
- **Modern Dark UI**: Elegant dark-themed interface with drag-and-drop support

## 📋 Requirements

- Python 3.7 or higher
- PyQt5 5.15.10+
- PyMuPDF (fitz) 1.23.8+
- PyPDF2 3.0.1+

## 🚀 Installation

### Option 1: Using pip

```bash
pip install PyQt5 PyMuPDF PyPDF2
```

### Option 2: Using requirements.txt

```bash
pip install -r requirements.txt
```

## 💻 Usage

### Basic Workflow

1. **Launch the application**:
   ```bash
   python main.py
   ```

2. **Select PDF file(s)**:
   - Click "Select PDF" button, or
   - Drag and drop PDF files into the application window

3. **Configure detection pattern**:
   - Choose from predefined patterns or create a custom regex pattern
   - Adjust grid settings if needed

4. **Detect references**:
   - Click "Detect References" to scan the PDF
   - View results in the table with page, column, row, and context information

5. **Customize styling** (optional):
   - Adjust highlight color, line width, animation type, etc.
   - Preview changes in real-time

6. **Generate interactive PDF**:
   - Click "Generate Interactive PDF"
   - The output PDF will contain clickable references with JavaScript highlighting

### Visual Grid Editor

For accurate coordinate calculation, you can manually define the grid:

1. Click "Open Visual Editor" button
2. Load your PDF
3. Switch between "Columns" and "Rows" modes
4. Click and drag on the PDF to draw grid lines
5. Configuration is automatically saved per PDF

### Supported Reference Patterns

The application supports multiple reference formats:

- **`/1.0-A`**: Standard format (Page.Column-Row)
- **`25-A.0`**: Alternative format (Page-Row.Column)
- **`A1/25`**: Row+Column/Page format
- **`(1-A-0)`**: Parentheses format
- **Custom**: Define your own regex pattern

### Configuration Files

The application uses two configuration files:

- **`grid_config.json`**: Stores grid positions for coordinate calculation
- **`styles_config.json`**: Stores styling preferences (colors, animations, etc.)

## 📁 Project Structure

```
ref/
├── main.py                 # Main application file
├── grid_config.json        # Grid configuration
├── styles_config.json      # Styling configuration
├── logo.png               # Application icon
├── logo.ico               # Application icon (Windows)
└── README.md              # This file
```

## 🎨 Customization

### Changing Highlight Colors

The application supports various color presets:
- Red, Blue, Green, Yellow, Orange, Purple, Cyan, Magenta
- Custom RGB values

### Adjusting Animation

- **Blink Speed**: Control how fast the highlight blinks (0-2000ms)
- **Duration**: How long the highlight remains visible (1-10 seconds)
- **Animation Type**: Choose between Blink, Pulse, Fade In/Out, or None

### Modifying Line Style

- **Solid**: Continuous line
- **Dashed**: Dashed line
- **Dotted**: Dotted line

## 🔧 Technical Details

### JavaScript Injection

The application injects JavaScript code into PDFs that:
- Creates a highlight field at the target coordinates
- Implements animation effects (blink, pulse, fade)
- Automatically removes the highlight after a specified duration
- Works with Adobe Acrobat Reader and compatible PDF viewers

### Coordinate Calculation

Coordinates are calculated based on:
- Grid positions (columns and rows)
- Page dimensions
- Reference format (page, column, row values)

### Reference Detection

Uses regex patterns to detect references in PDF text:
- Extracts page, column, and row information
- Captures surrounding context
- Handles various formats and edge cases

## 📊 Output

### Interactive PDF

The generated PDF includes:
- Clickable reference links
- JavaScript highlighting on click
- Visual annotations (blue borders)
- Tooltips with reference information

### JSON Export

Exports reference data in JSON format:
```json
{
  "full": "/1.0-A",
  "page": "1",
  "column": "0",
  "row": "A",
  "coordinates": [100.5, 200.3, 150.7, 220.8],
  "target_coordinates": [50.2, 100.4, 100.2, 150.4],
  "context": "Motor control circuit..."
}
```

## 🐛 Troubleshooting

### JavaScript not working
- Ensure you're using Adobe Acrobat Reader (not a web browser)
- Enable JavaScript in Acrobat preferences: Edit → Preferences → JavaScript → Enable Acrobat JavaScript

### Incorrect coordinates
- Use the Visual Grid Editor to manually define grid positions
- Adjust grid settings in the configuration
- Check that the reference format matches your PDF structure

### References not detected
- Verify the reference pattern matches your PDF format
- Try using a custom regex pattern
- Check that the PDF contains selectable text (not just images)

## 📝 Notes

- The application works best with PDFs containing selectable text
- For scanned PDFs, OCR preprocessing may be required
- JavaScript features require a compatible PDF viewer (Adobe Acrobat Reader recommended)
- Grid configuration is saved per PDF for future use

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available for personal use and modification. You are free to:
- Modify the code for your personal needs
- Use the software for personal, non-commercial purposes
- Share modifications with others

**Restrictions:**
- This software may not be used for commercial purposes or to generate profit
- No warranty is provided

## 🙏 Acknowledgments

Built with:
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) - GUI framework
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF processing
- [PyPDF2](https://pypdf2.readthedocs.io/) - PDF manipulation

---

**Note**: This application is designed for electrical schematic PDFs but can be adapted for other document types with reference systems.

