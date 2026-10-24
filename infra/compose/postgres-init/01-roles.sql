-- Faqat dev (birinchi ishga tushishda, bo'sh volume'da). Ilova shu rol bilan ulanadi: superuser emas,
-- BYPASSRLS yo'q, jadvallar egasi emas — RLS dev'da ham ishlaydi. Staging/prod rollari va parollari — B2.10 (sirlar).
CREATE ROLE up_app LOGIN PASSWORD 'up_app' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
