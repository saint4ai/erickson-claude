#!/usr/bin/env python3
"""Договор Erickson по шаблону: проверка данных и заполнение DOCX.

  python3 fill_contract.py templates
      какие размеченные шаблоны лежат в assets/
  python3 fill_contract.py fields --template "assets/<имя>.docx"
      какие поля нужны шаблону
  python3 fill_contract.py fill data.json --out "Договор.docx" --template "assets/<имя>.docx"
      проверить данные и заполнить шаблон

data.json:
  contract_date      "ГГГГ-ММ-ДД"
  price_base         цена по каталогу, целые тенге
  discount_percent   или discount_amount, необязательно
  payments           [{"date": "ГГГГ-ММ-ДД", "amount": 150000}, ...], от 1 до 12
  остальные поля шаблона строками; поля *_date тоже "ГГГГ-ММ-ДД"

Считает сам: discount_amount, price_final, payments_count.
Фильтры для шаблона: money, words_ru, words_kz, date, date_ru, date_kz.

Код выхода: 0 готово, 1 ошибки в данных, 2 нет шаблона или он сломан.
"""
import argparse
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import jinja2
from docxtpl import DocxTemplate
from num2words import num2words

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / 'assets'
COMPUTED = {'discount_amount', 'price_final', 'payments_count'}
MAX_PAYMENTS = 12
MONTHS_RU = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
             'августа', 'сентября', 'октября', 'ноября', 'декабря']
MONTHS_KZ = ['қаңтар', 'ақпан', 'наурыз', 'сәуір', 'мамыр', 'маусым', 'шілде',
             'тамыз', 'қыркүйек', 'қазан', 'қараша', 'желтоқсан']
IIN_FIELD = re.compile(r'(^|_)(iin|bin)(_|$)')


def make_env():
    env = jinja2.Environment()
    env.filters.update({
        'money': lambda v: f'{v:,}'.replace(',', ' '),
        'words_ru': lambda v: num2words(v, lang='ru'),
        'words_kz': lambda v: num2words(v, lang='kz'),
        'date': lambda d: d.strftime('%d.%m.%Y'),
        'date_ru': lambda d: f'{d.day} {MONTHS_RU[d.month - 1]} {d.year} г.',
        'date_kz': lambda d: f'{d.year} жылғы {d.day} {MONTHS_KZ[d.month - 1]}',
    })
    return env


def iin_ok(value):
    """Контрольная цифра ИИН/БИН: ловит ошибку в одной цифре при чтении с фото."""
    if not re.fullmatch(r'\d{12}', value):
        return False
    digits = [int(c) for c in value]
    for weights in (range(1, 12), (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)):
        check = sum(d * w for d, w in zip(digits, weights)) % 11
        if check != 10:
            return check == digits[11]
    return False


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def is_money(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def build_context(data, needed):
    errors = []
    ctx = {}

    for key in sorted(needed - COMPUTED - {'payments'}):
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f'{key}: нет значения, его требует шаблон')

    for key, value in data.items():
        if key in ('payments', 'price_base', 'discount_percent', 'discount_amount'):
            continue
        if key.endswith('date'):
            parsed = parse_date(value)
            if parsed is None:
                errors.append(f'{key}: дата должна быть в виде ГГГГ-ММ-ДД, сейчас {value!r}')
            ctx[key] = parsed
            continue
        if isinstance(value, str):
            value = value.strip()
            if IIN_FIELD.search(key) and value and not iin_ok(value):
                errors.append(f'{key}: {value} не проходит проверку ИИН/БИН, сверьте цифры с документом')
        ctx[key] = value

    price_base = data.get('price_base')
    if not is_money(price_base):
        errors.append('price_base: нужна цена целым числом тенге больше нуля')
        return ctx, errors

    percent, amount = data.get('discount_percent'), data.get('discount_amount')
    if percent is not None and amount is not None:
        errors.append('скидка: укажите либо discount_percent, либо discount_amount')
        return ctx, errors
    if percent is not None:
        if not isinstance(percent, (int, float)) or not 0 < percent < 100:
            errors.append('discount_percent: нужен процент больше 0 и меньше 100')
            return ctx, errors
        discount = price_base * percent / 100
        if discount != int(discount):
            errors.append(f'скидка {percent}% от {price_base} даёт дробную сумму {discount}, уточните итог у сотрудника')
            return ctx, errors
        amount = int(discount)
    elif amount is None:
        amount = 0
    elif not is_money(amount) or amount >= price_base:
        errors.append('discount_amount: нужна сумма целым числом, меньше цены')
        return ctx, errors

    price_final = price_base - amount
    ctx.update(price_base=price_base, discount_amount=amount, price_final=price_final)

    payments = data.get('payments')
    if not isinstance(payments, list) or not 1 <= len(payments) <= MAX_PAYMENTS:
        errors.append(f'payments: нужен график от 1 до {MAX_PAYMENTS} траншей')
        return ctx, errors
    rows, previous = [], None
    for n, p in enumerate(payments, 1):
        when = parse_date(p.get('date')) if isinstance(p, dict) else None
        sum_ = p.get('amount') if isinstance(p, dict) else None
        if when is None:
            errors.append(f'транш {n}: дата должна быть в виде ГГГГ-ММ-ДД')
        elif previous and when <= previous:
            errors.append(f'транш {n}: дата {when:%d.%m.%Y} не позже предыдущего транша')
        if not is_money(sum_):
            errors.append(f'транш {n}: сумма должна быть целым числом тенге больше нуля')
        previous = when or previous
        rows.append({'n': n, 'date': when, 'amount': sum_})
    if not errors:
        total = sum(r['amount'] for r in rows)
        if total != price_final:
            errors.append(f'сумма траншей {total} не равна итоговой цене {price_final} (разница {total - price_final})')
    ctx.update(payments=rows, payments_count=len(rows))
    return ctx, errors


def leftover_tags(path):
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith('word/') and name.endswith('.xml'):
                xml = z.read(name).decode('utf-8')
                if '{{' in xml or '{%' in xml:
                    return name
    return None


def plain(value):
    return value.isoformat() if isinstance(value, date) else value


def open_template(path):
    if not path.exists():
        print(f'Шаблон не найден: {path}. Список размеченных шаблонов: python3 ' + sys.argv[0] + ' templates.')
        sys.exit(2)
    return DocxTemplate(str(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('command', choices=['templates', 'fields', 'fill'])
    ap.add_argument('data', nargs='?')
    ap.add_argument('--out')
    ap.add_argument('--template', type=Path)
    args = ap.parse_args()

    if args.command == 'templates':
        print(json.dumps(sorted(p.name for p in ASSETS.glob('*.docx')), ensure_ascii=False))
        return

    if args.template is None:
        available = ', '.join(f'assets/{p.name}' for p in sorted(ASSETS.glob('*.docx')))
        print(f'Укажите шаблон: --template "assets/<имя>.docx". Доступны: {available}')
        sys.exit(2)
    template = args.template if args.template.is_absolute() else SKILL_DIR / args.template

    env = make_env()
    tpl = open_template(template)
    try:
        needed = tpl.get_undeclared_template_variables(jinja_env=env)
    except jinja2.TemplateError as e:
        print(f'Шаблон сломан: {e}')
        sys.exit(2)

    if args.command == 'fields':
        print(json.dumps({
            'collect': sorted(needed - COMPUTED - {'payments'}),
            'computed': sorted(needed & COMPUTED),
            'payments': 'payments' in needed,
        }, ensure_ascii=False, indent=2))
        return

    if not args.data or not args.out:
        ap.error('для fill нужны data.json и --out')
    data = json.loads(Path(args.data).read_text(encoding='utf-8'))
    ctx, errors = build_context(data, needed)
    if errors:
        print('Договор не собран, исправьте данные:')
        print('\n'.join(f'- {e}' for e in errors))
        sys.exit(1)

    tpl.render(ctx, jinja_env=env, autoescape=True)
    out = Path(args.out)
    tpl.save(str(out))
    part = leftover_tags(out)
    if part:
        out.unlink()
        print(f'В шаблоне осталась неразобранная метка {{{{ }}}} в {part}. Шаблон надо поправить.')
        sys.exit(2)

    print(json.dumps({
        'file': str(out),
        'price_base': ctx['price_base'],
        'discount_amount': ctx['discount_amount'],
        'price_final': ctx['price_final'],
        'payments': [{**r, 'date': plain(r['date'])} for r in ctx['payments']],
        'fields': {k: plain(v) for k, v in ctx.items()
                   if k not in COMPUTED | {'payments', 'price_base'}},
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
