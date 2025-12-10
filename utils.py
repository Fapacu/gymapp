# C:\Users\Acer\Desktop\gymapp\utils.py

from decimal import Decimal

def format_currency_robust(value):
    """
    Formatea un valor numérico (Decimal o float) a una cadena de moneda
    con separadores de miles y dos decimales, prefijado con '$'.
    """
    if value is None:
        return "$ 0.00"
    
    # Asegúrate de que el valor es Decimal para un formateo consistente
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except:
            return "$ 0.00"

    # Ejemplo de formato para moneda local (puedes ajustar el símbolo y la coma/punto)
    # Por ejemplo, para USD/Internacional: locale.currency(value, symbol='$', grouping=True)
    # Usaremos f-string con coma como separador de miles (ajustable)
    return f"$ {value:,.2f}" 

# ... (Si tienes más funciones auxiliares, ponlas aquí)