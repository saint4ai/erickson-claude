#!/usr/bin/env python3
"""КП Erickson по образцу: разбор DOCX и замена текста с сохранением оформления.

  python3 kp_from_sample.py inspect "КП Образец.docx"
      показать абзацы, таблицы и колонтитулы образца с номерами
  python3 kp_from_sample.py fill "КП Образец.docx" map.json --out "КП Клиент.docx"
      скопировать образец и заменить текст по map.json

map.json: [{"old": "было", "new": "стало", "count": 2}, ...]
  count необязателен: без него достаточно, чтобы фраза встретилась хоть раз,
  с ним фраза должна встретиться ровно count раз.

Замена находит фразу, даже если Word разбил её на несколько run внутри абзаца:
текст вставляется оформлением первого run совпадения, остальные run абзаца
не трогаются.

Код выхода: 0 готово, 1 ошибка в заменах или map.json, 2 образец не открывается.
"""
import argparse
import json
import sys
from pathlib import Path

from docx import Document


def para_text(p):
    return ''.join(r.text for r in p.runs)


def table_labeled(table, label):
    """Абзацы таблицы с номерами t1.r2.c3; вложенные таблицы тоже."""
    seen = set()
    for ri, row in enumerate(table.rows, 1):
        for ci, cell in enumerate(row.cells, 1):
            if id(cell._tc) in seen:  # объединённая ячейка повторяется
                continue
            seen.add(id(cell._tc))
            pars = list(cell.paragraphs)
            base = f'{label}.r{ri}.c{ci}'
            for i, p in enumerate(pars, 1):
                yield (base if len(pars) == 1 else f'{base}.p{i}'), p
            for ni, nested in enumerate(cell.tables, 1):
                yield from table_labeled(nested, f'{base}.t{ni}')


def iter_labeled(doc):
    for i, p in enumerate(doc.paragraphs, 1):
        yield f'p{i}', p
    for ti, table in enumerate(doc.tables, 1):
        yield from table_labeled(table, f't{ti}')
    sections = doc.sections
    for si, sec in enumerate(sections):
        s = '' if len(sections) == 1 else f's{si + 1}.'
        for part, name in ((sec.header, 'header'), (sec.footer, 'footer')):
            for i, p in enumerate(part.paragraphs, 1):
                yield f'{s}{name}.p{i}', p
            for ti, table in enumerate(part.tables, 1):
                yield from table_labeled(table, f'{s}{name}.t{ti}')


def all_paragraphs(doc):
    seen = set()
    pars = []
    for _, p in iter_labeled(doc):
        if id(p._p) not in seen:
            seen.add(id(p._p))
            pars.append(p)
    return pars


def cmd_inspect(args):
    doc = Document(args.sample)
    body, chrome = [], []
    for label, p in iter_labeled(doc):
        text = para_text(p)
        if not text.strip():
            continue
        target = chrome if 'header' in label or 'footer' in label else body
        target.append(f'{label}\t{text}')
    out = ['— Абзацы и таблицы документа'] + body
    if chrome:
        out += ['— Колонтитулы'] + chrome
    print('\n'.join(out))


def replace_in_paragraph(p, old, new):
    """Заменить все вхождения old в абзаце; оформить new первым run совпадения."""
    made, offset = 0, 0
    while True:
        runs = p.runs
        full = ''.join(r.text for r in runs)
        start = full.find(old, offset)
        if start < 0:
            return made
        end = start + len(old)
        spans = []  # (индекс run, начало, конец) — runs, попавшие в совпадение
        pos = 0
        for i, r in enumerate(runs):
            stop = pos + len(r.text)
            if stop > start and pos < end:
                spans.append((i, pos, stop))
            pos = stop
        first_i, first_start, _ = spans[0]
        last_i, last_start, _ = spans[-1]
        prefix = runs[first_i].text[: start - first_start]
        suffix = runs[last_i].text[end - last_start:]
        if first_i == last_i:  # совпадение целиком внутри одного run
            runs[first_i].text = prefix + new + suffix
        else:
            runs[first_i].text = prefix + new
            for i in range(first_i + 1, last_i):
                runs[i].text = ''
            runs[last_i].text = suffix
        made += 1
        offset = start + len(new)  # новый текст может содержать old: дальше ищем после него


def fail(message):
    print(message)
    sys.exit(1)


def load_map(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        fail(f'Не удалось прочитать map.json: {e}')
    if not isinstance(data, list) or not data:
        fail('map.json должен быть непустым списком {"old": ..., "new": ...}')
    items = []
    for n, item in enumerate(data, 1):
        if not isinstance(item, dict) or not isinstance(item.get('old'), str) or not item['old'] \
                or not isinstance(item.get('new'), str):
            fail(f'Запись {n} в map.json: нужны old (непустая строка) и new (строка)')
        count = item.get('count', 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            fail(f'Запись {n} в map.json: count должен быть целым числом не меньше 0')
        items.append((item['old'], item['new'], count))
    return items


def cmd_fill(args):
    try:
        doc = Document(args.sample)
    except Exception as e:
        print(f'Не удалось открыть образец: {e}')
        sys.exit(2)
    items = load_map(args.map)
    pars = all_paragraphs(doc)

    # проверка до записи: каждый old найден нужное число раз, файл не создаётся
    problems = []
    for old, _, count in items:
        found = sum(para_text(p).count(old) for p in pars)
        if found == 0:
            problems.append(f'не найдено: «{old}»')
        elif count and found != count:
            problems.append(f'«{old}»: найдено {found}, ожидалось {count}')
    if problems:
        fail('Ошибки в заменах, файл не создан:\n' + '\n'.join(problems))

    report = []
    for old, new, count in items:
        made = sum(replace_in_paragraph(p, old, new) for p in pars)
        if count and made != count:
            fail(f'После предыдущих замен «{old}» заменена {made} раз, ожидалось {count}. Файл не создан.')
        report.append({'old': old, 'new': new, 'count': made})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(json.dumps({'file': str(out), 'replacements': report}, ensure_ascii=False))


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='КП Erickson по образцу DOCX')
    sub = parser.add_subparsers(dest='command', required=True)

    p_inspect = sub.add_parser('inspect', help='показать абзацы, таблицы и колонтитулы с номерами')
    p_inspect.add_argument('sample')

    p_fill = sub.add_parser('fill', help='заменить текст по map.json с сохранением оформления')
    p_fill.add_argument('sample')
    p_fill.add_argument('map')
    p_fill.add_argument('--out', required=True)

    args = parser.parse_args()
    (cmd_inspect if args.command == 'inspect' else cmd_fill)(args)


if __name__ == '__main__':
    main()
