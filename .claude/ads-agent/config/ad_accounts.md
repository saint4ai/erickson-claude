# Ad Accounts

Список рекламных аккаунтов для управления через Claude Ads Agent.

---

## Как добавить аккаунт

1. Добавь секцию ниже с информацией об аккаунте
2. Создай бриф в `briefs/{account_name}.md` (используй `briefs/_template.md`)
3. Убедись что токен MCP сервера имеет доступ к аккаунту

---

## Аккаунт 1: Erickson

- **Account ID**: act_560203557693988 (Erickson International)
- **Page ID**: XXXXXXXXX (заполним на уроке)
- **Instagram ID**: XXXXXXXXX (заполним на уроке)
- **Название**: Erickson
- **Сайт**: (заполним на уроке)
- **Бриф**: briefs/erickson.md (создадим на уроке по briefs/_template.md)
- **Статус**: активен
- **Валюта**: USD
- **Часовой пояс**: UTC+5 (Алматы)
- **Тип конверсии**: (заполним на уроке)
- **Заметки**: учебный центр Erickson, программы коучинга

---

## Пример формата аккаунта

```markdown
## Аккаунт N: {Название}

- **Account ID**: act_XXXXXXXXX
- **Page ID**: XXXXXXXXX
- **Instagram ID**: XXXXXXXXX
- **Название**: {Название в Facebook}
- **Сайт**: https://example.com
- **Бриф**: [briefs/{filename}.md](briefs/{filename}.md)
- **Статус**: активен | приостановлен | архив
- **Валюта**: USD | KZT | RUB | ...
- **Часовой пояс**: UTC+X ({Город})
- **Тип конверсии**: Lead-формы | WhatsApp | Site Leads (Pixel)
- **Заметки**: {Краткое описание}
```

---

## Где найти ID

### Account ID
1. Facebook Ads Manager -> Настройки аккаунта
2. Или в URL: `https://adsmanager.facebook.com/adsmanager/manage/accounts?act=XXXXXXXXX`

### Page ID
1. Facebook Page -> О странице -> Прозрачность страницы
2. Или: https://findmyfbid.in/

### Instagram ID
1. Через MCP: `get_account_pages(account_id)` вернёт instagram_accounts
2. Или в Business Suite: Instagram -> Настройки

---

## Статусы аккаунтов

| Статус | Описание |
|--------|----------|
| **активен** | Аккаунт в работе, можно оптимизировать |
| **приостановлен** | Временно не работаем, не трогать |
| **архив** | Не используется, только для истории |
