#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neo4j 知识图谱查询模块（阶段 2 · 任务 2.2）

提供"文物 → 时期/文化（含时间范围）"的查询函数。
驱动连接模块级缓存，避免重复创建。
"""
import os

from neo4j import GraphDatabase

# 模块级缓存：驱动只创建一次
_driver = None


def get_driver(uri: str, user: str, password: str):
    """获取（或复用）Neo4j 驱动"""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver


def query_artifact_info(object_id: str, uri: str, user: str, password: str):
    """
    查询单件文物的图谱信息：所属时期（含 Wikidata 时间范围）、所属文化。
    返回 dict（无匹配时返回空 dict）：
      {
        "period": 时期名, "period_start": 起始年, "period_end": 结束年,
        "culture": 文化名, "culture_label": Wikidata 标签, "culture_qid": Wikidata QID
      }
    """
    driver = get_driver(uri, user, password)
    with driver.session() as session:
        recs = session.run(
            "MATCH (a:Artifact {object_id:$oid}) "
            "OPTIONAL MATCH (a)-[:BELONGS_TO]->(p:Period) "
            "OPTIONAL MATCH (a)-[:BELONGS_TO_CULTURE]->(c:Culture) "
            "RETURN p.name AS period, p.start AS period_start, p.end AS period_end, "
            "       c.name AS culture, c.wd_label AS culture_label, c.qid AS culture_qid",
            oid=object_id,
        ).data()
    return recs[0] if recs else {}
