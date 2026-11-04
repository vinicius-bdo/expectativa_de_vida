SELECT
    p.pais,
    ROUND(AVG(f.expectativa_de_vida), 1) AS expectativa_media_anos
FROM marts.fato_gastos AS f
JOIN marts.d_pais AS p USING (id_pais)
WHERE f.expectativa_de_vida IS NOT NULL
GROUP BY p.pais
ORDER BY expectativa_media_anos DESC;