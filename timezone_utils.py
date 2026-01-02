"""
timezone_utils.py - Utilitários para conversão de fuso horário
Fuso padrão: EST (Eastern Standard Time) - America/New_York
"""

from datetime import datetime, timedelta

# Offset para EST (UTC-5) - durante horário padrão
# Durante DST (Daylight Saving Time) seria UTC-4
EST_OFFSET_HOURS = -5


def utc_to_est(dt: datetime) -> datetime:
    """
    Converte datetime UTC para EST (Eastern Standard Time).
    Nota: Esta é uma conversão simples que não considera DST.
    Para produção com DST, usar pytz ou zoneinfo.
    """
    if dt is None:
        return None

    try:
        # Se o datetime já tem timezone info, assumir que está em UTC
        # Caso contrário, assumir UTC
        return dt + timedelta(hours=EST_OFFSET_HOURS)
    except Exception:
        return dt


def format_datetime_est(dt: datetime, format_str: str = "%m/%d/%Y %H:%M") -> str:
    """
    Formata datetime para string no fuso EST.

    Args:
        dt: datetime object (assumido como UTC)
        format_str: formato de saída (padrão: MM/DD/YYYY HH:MM)

    Returns:
        String formatada no fuso EST
    """
    if dt is None:
        return "N/A"

    try:
        est_dt = utc_to_est(dt)
        return est_dt.strftime(format_str)
    except Exception:
        return str(dt)


def format_time_est(dt: datetime, format_str: str = "%H:%M:%S") -> str:
    """
    Formata apenas hora no fuso EST.
    """
    if dt is None:
        return "N/A"

    try:
        est_dt = utc_to_est(dt)
        return est_dt.strftime(format_str)
    except Exception:
        return str(dt)[:8] if dt else "N/A"


def format_date_est(dt: datetime, format_str: str = "%m/%d/%Y") -> str:
    """
    Formata apenas data no fuso EST.
    """
    if dt is None:
        return "N/A"

    try:
        est_dt = utc_to_est(dt)
        return est_dt.strftime(format_str)
    except Exception:
        return str(dt)[:10] if dt else "N/A"


def now_est() -> datetime:
    """
    Retorna datetime atual no fuso EST.
    """
    return datetime.utcnow() + timedelta(hours=EST_OFFSET_HOURS)
