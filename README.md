# FacturaPro

Aplicación de escritorio para Windows, **100% local**, que convierte una carpeta de
facturas (PDF con texto, PDF escaneados y fotos JPG/PNG) en un archivo Excel estructurado.

**Ningún dato sale del ordenador.** No se envía nada a internet: ni PDFs, ni NIFs,
ni importes. El OCR se ejecuta localmente con Tesseract.

## Requisitos en Windows

1. **Python 3.10+** → https://python.org (marca la casilla *Add Python to PATH*)
2. **Tesseract OCR** (solo si necesitas procesar escaneados/fotos)
   → instalador UB-Mannheim: https://github.com/UB-Mannheim/tesseract/wiki
   Durante la instalación añade el idioma **Spanish**.
   Si no está en el PATH, define la variable:
   ```bat
   set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
   ```

## Instalación (desarrollo)

```bat
git clone <url-del-repositorio> FacturaPro
cd FacturaPro
pip install -r requirements-dev.txt
```

## Ejecutar

Interfaz gráfica:
```bat
python main.py
```

Modo consola (sin interfaz, útil para probar):
```bat
python main.py --cli sample_invoices facturas_procesadas.xlsx
```

Flujo: **Seleccionar carpeta → Procesar facturas → Exportar a Excel**.

## Tests

```bat
pytest -p no:libtmux
```

Se generan facturas sintéticas automáticamente (PDF con texto, PDF escaneado y foto JPG).

## Generar el .exe

```bat
pip install -r requirements-build.txt
pyinstaller --noconsole --onefile --name FacturaPro ^
    --collect-all customtkinter ^
    --collect-all pytesseract ^
    main.py
```
Resultado: `dist\FacturaPro.exe`. Puedes copiarlo o enviarlo tal cual; el cliente solo
necesita tener Tesseract instalado si quiere procesar escaneados/fotos.

### Instalador (opcional)

Con Inno Setup (https://jrsoftware.org/isinfo.php) crea `FacturaPro_Setup.exe`
incluyendo el contenido de `dist\`.

## Estructura

```
app/
├── models/       # InvoiceResult, estados (OK / REVISAR / ERROR)
├── pdf/          # Lectura PyMuPDF + detección de PDF sin texto
├── ocr/          # Motor OCR local (intercambiable)
├── extraction/   # NIF, proveedor, importes (heurísticas, no posiciones fijas)
├── validation/   # Base + IVA = Total, formato de NIF, valores imposibles
├── excel/        # Exportación profesional (filtros, moneda, cabecera congelada)
├── services/     # Procesamiento por lotes en segundo plano + licencia (preparada)
├── ui/           # Interfaz CustomTkinter
└── utils/        # Parseo numérico español (1.234,56), logging local
```

## Si una factura no se interpreta

No se inventan datos: queda marcada como **REVISAR** (campo ausente o descuadre
aritmético) o **ERROR** (archivo ilegible) con una advertencia explicativa en el Excel.
Revisa `logs\facturapro.log` para más detalle.
