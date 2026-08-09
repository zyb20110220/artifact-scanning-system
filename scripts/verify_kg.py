#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图谱验证脚本：查询文物关系 + 抽查 Wikidata 补全的时间范围"""
import os
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://neo4j:7687", auth=("neo4j", os.environ.get("NEO4J_PASSWORD", ""))
)
s = driver.session()

print("=== 查询文物 36444 的图谱关系 ===")
rows = s.run(
    "MATCH (a:Artifact {object_id:'36444'}) "
    "OPTIONAL MATCH (a)-[:BELONGS_TO]->(p:Period) "
    "OPTIONAL MATCH (a)-[:BELONGS_TO_CULTURE]->(c:Culture) "
    "RETURN a.title AS title, p.name AS period, p.start AS p_start, "
    "p.end AS p_end, c.name AS culture"
).data()
for r in rows:
    print("  {} | 时期: {} | 文化: {}".format(
        r.get("title", "-"), r.get("period", "-"), r.get("culture", "-")))

print("=== 抽查 Period 时间范围（Wikidata 补全）===")
rows2 = s.run(
    "MATCH (p:Period) WHERE p.start IS NOT NULL AND p.start <> '' "
    "RETURN p.name AS name, p.start AS start, p.end AS end, p.qid AS qid LIMIT 8"
).data()
for r in rows2:
    print("  {}: {} ~ {} (qid={})".format(
        r.get("name", "-"), r.get("start", "-"), r.get("end", "-"), r.get("qid", "-")))

print("=== 抽查 Culture 节点 ===")
rows3 = s.run(
    "MATCH (c:Culture) WHERE c.qid IS NOT NULL AND c.qid <> '' "
    "RETURN c.name AS name, c.wd_label AS wd_label, c.qid AS qid LIMIT 8"
).data()
for r in rows3:
    print("  {} ({}): qid={}".format(r.get("name", "-"), r.get("wd_label", "-"), r.get("qid", "-")))

driver.close()
