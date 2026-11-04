SELECT
    p.pais,
    sum(f.gasto_usd) as gasto_usd
FROM marts.fato_gastos AS f
JOIN marts.d_calendario AS d USING (id_calendario)
JOIN marts.d_pais AS p USING (id_pais)
WHERE f.gasto_usd IS NOT NULL
group by p.pais
ORDER BY 2;