from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from src.Config import (MONTH_RANGE_past, MONTH_RANGE_future, DAY_RANGE_past, DAY_RANGE_future)

class DateTimeUtils:
    """
    Esta classe fornece funções utilitárias para trabalhar com datas e horas.
    """
    
    @staticmethod
    def get_current_datetime():
        # ... (seu método original)
        now = datetime.now()
        date_time = now.strftime("%d-%m-%Y__%H-%M-%S")
        return date_time
    
    @staticmethod
    def format_date_sap(date_obj, format_str='%d.%m.%Y'):
        """
        Formata um objeto de data...
        
        Retorna:
            str: A data formatada.
        """
        return date_obj.strftime(format_str)
    
    @staticmethod
    def get_day_range():
        today = date.today()
        days_ago = today - relativedelta(days=DAY_RANGE_past)
        days_ahead = today + relativedelta(days=DAY_RANGE_future)
        
        formatted_past_date = DateTimeUtils.format_date_sap(days_ago)
        formatted_future_date = DateTimeUtils.format_date_sap(days_ahead)
        return (formatted_past_date, formatted_future_date)
    
    @staticmethod
    def get_month_range():
        """
        Calcula as datas MONTH_RANGE meses antes e MONTH_RANGE meses depois de hoje.
        obs: MONTH_RANGE é uma variável configurável em src/CONFIG.py
        Retorna:
            tuple: Uma tupla contendo duas strings de data (data_passada, data_futura)
                   no formato 'dd.mm.yyyy'.
        """
        today = date.today()

        # Calcula MONTH_RANGE meses atrás
        months_ago = today - relativedelta(months=MONTH_RANGE_past)
        
        # Calcula MONTH_RANGE meses à frente
        months_ahead = today + relativedelta(months=MONTH_RANGE_future)

        # Formata as datas usando seu método existente
        formatted_past_date = DateTimeUtils.format_date_sap(months_ago)
        formatted_future_date = DateTimeUtils.format_date_sap(months_ahead)
        
        return (formatted_past_date, formatted_future_date)