from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def build_receipt_pdf(data: dict) -> bytes:
    """
    Genera un comprobante de pago en formato PDF.

    data debe contener: numero, fecha, cliente, cedula, importe, metodo, 
    tipo, periodo, vence.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Mapeo de claves a etiquetas en español para una mejor presentación
    etiquetas = {
        "numero": "Recibo No.",
        "fecha": "Fecha de Pago",
        "cliente": "Cliente",
        "cedula": "Cédula",
        "importe": "Importe Total",
        "metodo": "Método de Pago",
        "tipo": "Tipo de Suscripción",
        "periodo": "Período Cubierto",
        "vence": "Fecha de Vencimiento"
    }

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h-50, "Comprobante de Pago")

    c.setFont("Helvetica", 12)
    y = h - 90
    
    # Imprimir los datos del diccionario
    for k in ["numero","fecha","cliente","cedula","importe","metodo","tipo","periodo","vence"]:
        if k in data:
            label = etiquetas.get(k, k.capitalize())
            c.drawString(40, y, f"{label}: {data[k]}")
            y -= 20

    c.line(40, y-10, w-40, y-10)
    c.drawString(40, y-30, "Gracias por su pago.")
    c.showPage()
    c.save()
    return buf.getvalue()

def build_routine_pdf(cab: dict, contenido: str) -> bytes:
    """
    Genera una rutina de ejercicios en formato PDF.

    cab debe contener: cliente, rutina, objetivo, observaciones, 
    asignada_desde, asignada_hasta.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h-50, "Rutina Personalizada")

    c.setFont("Helvetica", 12)
    y = h-90
    # Mapeo de cabeceras en español
    etiquetas_cab = {
        "cliente": "Cliente",
        "rutina": "Rutina",
        "objetivo": "Objetivo",
        "observaciones": "Observaciones",
        "asignada_desde": "Vigente Desde",
        "asignada_hasta": "Vigente Hasta"
    }
    
    for label in ["cliente","rutina","objetivo","observaciones","asignada_desde","asignada_hasta"]:
        if label in cab and cab[label]:
            display_label = etiquetas_cab.get(label, label.replace('_',' ').capitalize())
            c.drawString(40, y, f"{display_label}: {cab[label]}")
            y -= 18

    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Contenido / Plan:")
    y -= 20
    c.setFont("Helvetica", 11)

    # Imprimir el contenido de la rutina línea por línea
    for line in (contenido or "").splitlines():
        if y < 60:
            c.showPage()
            y = h - 60
            c.setFont("Helvetica", 11)
        c.drawString(40, y, line)
        y -= 14

    c.showPage()
    c.save()
    return buf.getvalue()