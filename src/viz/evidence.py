#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证据链网络图模块（阶段 4 · 任务 4.2）

把"查询文物 → 相似文物 → 时期/文化"关系绘制成网络图，
直观展示检索的证据链。用 networkx 布局 + matplotlib 绘制。
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                      # 非交互后端，供服务器环境使用
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

# 节点类型与颜色
KIND_COLORS = {
    "query": "red",
    "artifact": "skyblue",
    "period": "lightgreen",
    "culture": "orange",
}
KIND_LABELS = {
    "query": "Query Image",
    "artifact": "Artifact",
    "period": "Period",
    "culture": "Culture",
}


def build_evidence_graph(query_path, results, seed=42):
    """
    构建证据链网络图。

    参数：
      query_path  查询图片路径
      results     search_by_image 的返回值（含 image_path, score, kg）
    返回：
      matplotlib Figure（可直接交给 gr.Plot）
    """
    G = nx.Graph()
    q_label = Path(query_path).name
    G.add_node(q_label, kind="query")

    for r in results:
        oid = Path(r["image_path"]).name
        kg = r.get("kg") or {}
        G.add_node(oid, kind="artifact")
        G.add_edge(q_label, oid, weight=r.get("score", 0))

        # 时期/文化节点（从图谱查询获得）
        period = kg.get("period")
        culture = kg.get("culture")
        if period:
            G.add_node(period, kind="period")
            G.add_edge(oid, period)
        if culture:
            G.add_node(culture, kind="culture")
            G.add_edge(oid, culture)

    # 布局：按节点类型分层（查询在左，文物居中，时期/文化在右）
    pos = nx.spring_layout(G, seed=seed, k=1.2)

    node_colors = [KIND_COLORS.get(G.nodes[n].get("kind"), "gray") for n in G.nodes]
    edge_widths = [1 + 3 * G.edges[e].get("weight", 0) for e in G.edges]

    fig, ax = plt.subplots(figsize=(11, 7))
    nx.draw_networkx(
        G, pos, ax=ax, with_labels=True,
        node_color=node_colors, node_size=1600,
        font_size=8, edge_color="gray",
        width=edge_widths, alpha=0.9,
    )

    # 图例
    legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=c,
               label=KIND_LABELS[k], markersize=10)
        for k, c in KIND_COLORS.items()
    ]
    ax.legend(handles=legend, loc="best", frameon=True)
    ax.set_title("Evidence Chain Graph (query -> similar artifacts -> period/culture)")
    ax.axis("off")
    plt.tight_layout()
    return fig
