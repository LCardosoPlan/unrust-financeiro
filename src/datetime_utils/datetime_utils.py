from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from src.Config import (
    MONTH_RANGE_past,
    MONTH_RANGE_future,
    DAY_RANGE_past,
    DAY_RANGE_FUTURE,
    FISCAL_YEAR_START_MONTH,
)

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
        days_ahead = today + relativedelta(days=DAY_RANGE_FUTURE)
        
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

    @staticmethod
    def get_fiscal_year(reference_date: date = None) -> str:
        """
        Devolve o ano fiscal da Plan para a data de referencia.

        O exercicio comeca em FISCAL_YEAR_START_MONTH (julho = mes 1), portanto
        de julho a dezembro o ano fiscal ja e o ano civil seguinte.
        Ex.: 28.08.2026 -> "2027"; 20.03.2026 -> "2026".
        """
        ref = reference_date or date.today()
        ano = ref.year + 1 if ref.month >= FISCAL_YEAR_START_MONTH else ref.year
        return str(ano)

    @staticmethod
    def get_fiscal_period(reference_date: date = None) -> int:
        """
        Devolve o periodo contabil (1..12) dentro do ano fiscal.
        Julho = 1, agosto = 2, ..., junho = 12.
        """
        ref = reference_date or date.today()
        return (ref.month - FISCAL_YEAR_START_MONTH) % 12 + 1

    @staticmethod
    def get_previous_fiscal_period(reference_date: date = None) -> tuple:
        """
        Devolve o periodo contabil a ser reportado: sempre o mes anterior.

        Regra:
          - estamos no periodo N (N > 1) -> reporta o periodo N-1 do mesmo
            ano fiscal. Ex.: agosto (periodo 2) -> periodo 1 (julho).
          - estamos no periodo 1 (julho)  -> reporta o periodo 12 (junho) do
            ano fiscal anterior.

        Retorna:
            tuple: (ano_fiscal: str, periodo: int)
        """
        ref = reference_date or date.today()
        periodo_atual = DateTimeUtils.get_fiscal_period(ref)
        ano_fiscal = int(DateTimeUtils.get_fiscal_year(ref))

        if periodo_atual == 1:
            return (str(ano_fiscal - 1), 12)
        return (str(ano_fiscal), periodo_atual - 1)
