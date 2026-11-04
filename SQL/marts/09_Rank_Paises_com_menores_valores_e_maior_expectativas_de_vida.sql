WITH medias AS (
    SELECT
        p.id_pais,
        p.pais,
        AVG(f.gasto_usd) AS gasto_medio_usd,
        AVG(f.expectativa_de_vida) AS expectativa_media_anos
    FROM marts.fato_gastos AS f
    JOIN marts.d_pais AS p USING (id_pais)
    GROUP BY p.id_pais, p.pais
)
SELECT
    pais,
    ROUND(gasto_medio_usd, 2) AS gasto_medio_usd,
   -- RANK() OVER (ORDER BY gasto_medio_usd ASC) AS rank_menor_gasto,
    ROUND(expectativa_media_anos, 2) AS expectativa_media_anos,
    RANK() OVER (ORDER BY expectativa_media_anos DESC) AS rank_maior_expectativa
FROM medias
ORDER BY rank_maior_expectativa--, rank_menor_gasto;