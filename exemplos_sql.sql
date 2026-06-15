-- exemplos_sql.sql
-- Consultas SQL de exemplo para o banco linkedin_profile.db
-- Execute com: sqlite3 data/linkedin_profile.db < exemplos_sql.sql
--          ou: sqlite3 data/linkedin_profile.db

-- ─────────────────────────────────────────
-- 1. Todas as coletas realizadas
-- ─────────────────────────────────────────
SELECT id, nome, titulo, data_coleta
FROM perfil
ORDER BY data_coleta DESC;

-- ─────────────────────────────────────────
-- 2. Perfil mais recente (dados completos)
-- ─────────────────────────────────────────
SELECT *
FROM perfil
ORDER BY id DESC
LIMIT 1;

-- ─────────────────────────────────────────
-- 3. Todas as experiências do perfil mais recente
-- ─────────────────────────────────────────
SELECT e.cargo, e.empresa, e.periodo, e.descricao
FROM experiencias e
JOIN perfil p ON e.perfil_id = p.id
WHERE p.id = (SELECT MAX(id) FROM perfil)
ORDER BY e.id;

-- ─────────────────────────────────────────
-- 4. Formação acadêmica mais recente
-- ─────────────────────────────────────────
SELECT f.instituicao, f.curso, f.periodo
FROM formacoes f
WHERE f.perfil_id = (SELECT MAX(id) FROM perfil);

-- ─────────────────────────────────────────
-- 5. Competências mais recentes
-- ─────────────────────────────────────────
SELECT competencia
FROM competencias
WHERE perfil_id = (SELECT MAX(id) FROM perfil)
ORDER BY competencia;

-- ─────────────────────────────────────────
-- 6. Certificações mais recentes
-- ─────────────────────────────────────────
SELECT nome, instituicao, data_emissao
FROM certificacoes
WHERE perfil_id = (SELECT MAX(id) FROM perfil);

-- ─────────────────────────────────────────
-- 7. Histórico de empresas em todas as coletas
-- ─────────────────────────────────────────
SELECT DISTINCT e.empresa, e.cargo, e.periodo
FROM experiencias e
ORDER BY e.empresa;

-- ─────────────────────────────────────────
-- 8. Competências que apareceram em mais de uma coleta
-- ─────────────────────────────────────────
SELECT competencia, COUNT(*) AS vezes_coletada
FROM competencias
GROUP BY competencia
HAVING COUNT(*) > 1
ORDER BY vezes_coletada DESC;

-- ─────────────────────────────────────────
-- 9. Comparação de títulos entre coletas
-- ─────────────────────────────────────────
SELECT id, titulo, data_coleta
FROM perfil
ORDER BY data_coleta;

-- ─────────────────────────────────────────
-- 10. Dados brutos da última coleta (JSON extraído)
-- ─────────────────────────────────────────
SELECT origem, data_coleta, length(conteudo_bruto) AS bytes_html
FROM dados_brutos
WHERE perfil_id = (SELECT MAX(id) FROM perfil);
