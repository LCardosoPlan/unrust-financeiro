# Classe DateTimeUtils

Essa classe fornece funções utilitárias para trabalhar com datas e horas.

### Métodos:
* `get_current_datetime(self) (método estático)`

    > * Retorna a data e hora atuais formatadas como `DD-MM-YYYY__HH-MM-SS`.<br>

<br>

* `format_date_sap(self, date_obj, format_str='%d.%m.%Y') (método estático)`
    > * Formata um objeto de data de acordo com a cadeia de caracteres de formato especificada (padrão: `"%d.%m.%Y"`).<br>
    > * A string de formato segue as diretivas [strftime padrão](https://strftime.org/)<br>

<br>

* `get_date_range(self) (método estático)`
    > * Calcula e retorna uma tupla contendo três datas formatadas:<br>
    >   - A data atual formatada de acordo com o padrão SAP (padrão: `"%d.%m.%Y"`).<br>
    >   - A data 30 dias antes da data atual, formatada de acordo com o padrão SAP.<br>
    >   - A data 180 dias após a data atual, formatada de acordo com o padrão SAP.

