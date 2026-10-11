# UPSTREAM — снапшот канона школ (school-portal)

- Источник: C:\Users\volga\schools-map-mathex\data\entities.json (активный клон schools-map-mathex)
- Коммит: 4455cc8 (base_mismatch 3-я очередь: isochrone_base для 10 школ)
- Дата снапшота: 2026-10-11
- md5: 04d56d81461df4e2e78bc19a67e56f1b
- Файл: data/upstream/entities_20261011_basefix.json
- ПРАВИЛО: канон не правится из этого проекта; при изменении канона — новый снапшот и пересчёт затронутых школ.
- build_schools_csv.py берёт самый свежий снапшот (max по имени) и уважает
  сущность.isochrone_base при выборе базовой точки.
