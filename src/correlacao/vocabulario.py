"""
Vocabulario fechado de 'Custo / Despesa Adm'.

A 'Base De-Para' col. H tem os mesmos conceitos escritos de varias maneiras:
'Patrimonio' sem acento, 'patrimonio' em minusculas, 'Patrimonio' com acento
agudo ou circunflexo; 'receita' e 'Receita'. Cada variacao vira uma categoria
separada nas tabelas dinamicas a jusante. Aqui todas colapsam num termo
canonico, e qualquer termo novo e recusado em vez de passar despercebido.

O termo canonico e o mais frequente na tabela mestra, escrito exatamente como
la esta - e o que o time contabil ja le nos relatorios. Trocar a grafia do
canonico muda a saida de milhares de linhas, portanto nao e detalhe de estilo:
altere TERMOS so com decisao explicita.
"""

import unicodedata

# Termos aceites na saida. Qualquer outro valor e erro de cadastro.
TERMOS = ("Custo", "Despesa", "Despesa Financeira", "Património", "Receita")


def _dobrar(texto: str) -> str:
    """Minusculas, sem acentos, espacos colapsados - so para comparar."""
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.split()).casefold()


_INDICE = {_dobrar(t): t for t in TERMOS}


def normalizar_custo_despesa(valor, estrito: bool = True) -> str:
    """
    Colapsa uma variacao de rotulo no termo canonico.

    Vazio devolve "" (o chamador decide se isso e 'Validacao'). Termo
    desconhecido levanta ValueError quando estrito=True - preferimos parar a
    carga da tabela mestra a propagar uma categoria fantasma para o resultado.
    """
    from src.correlacao.chaves import canonizar

    texto = canonizar(valor)
    if not texto:
        return ""
    termo = _INDICE.get(_dobrar(texto))
    if termo is None:
        if estrito:
            raise ValueError(
                f"Rotulo desconhecido em 'Custo / Despesa Adm': {texto!r}. "
                f"Vocabulario aceite: {', '.join(TERMOS)}."
            )
        return texto
    return termo
