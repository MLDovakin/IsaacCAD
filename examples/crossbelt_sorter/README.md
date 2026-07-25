# Проект kcad

## Рабочий цикл (не пропускать шаги)

```bash
python -m kcad.cli inspect --project .          # 1. прочитать фактическое состояние
# 2. правки — ТОЛЬКО в spec/machine.yaml
python -m kcad.cli build   --project .          # 3. полная пересборка
python -m kcad.cli check   --project .          # 4. инварианты
python -m kcad.cli golden  --project . --strict # 5. что изменилось против эталона
python -m kcad.cli views   --project . --capture # 6. скрины (для человека)
```

Первый прогон: `python -m kcad.cli golden --project . --save` — зафиксировать эталон.

В Isaac Sim добавляйте `--backend usd`, запуская из его питона:
```bash
./python.sh -m kcad.cli build --project /path/to/project --backend usd
```

## Структура

| Путь | Что это |
|---|---|
| `spec/machine.yaml` | единственный источник истины: параметры, фреймы, детали, джойнты, инварианты |
| `project/checks/` | проектные проверки (`@check`) |
| `project/steps/` | проектные runtime-шаги (`@step`) |
| `golden/` | эталонные снимки геометрии для регрессий |
| `out/` | стейджи USD и скрины (артефакты, не источник истины) |
