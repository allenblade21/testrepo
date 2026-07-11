"""SQLite 数据层。

从 seed_data 建库并提供按平台读取条目的接口，供各平台适配器调用。
使用内存库（:memory: 的替代——共享缓存文件），进程启动时初始化。
"""
from __future__ import annotations

import sqlite3

import seed_data
from .models import DeliveryPolicy, Listing, Promotion


def init_db(path: str = ":memory:") -> sqlite3.Connection:
    """建库、写入种子数据，返回连接。"""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS listing;
        DROP TABLE IF EXISTS promotion;
        DROP TABLE IF EXISTS delivery;
        CREATE TABLE listing (
            id INTEGER PRIMARY KEY,
            platform TEXT, merchant TEXT, brand TEXT, name TEXT, spec TEXT, type TEXT,
            barcode TEXT, list_price INTEGER, sale_price INTEGER
        );
        CREATE TABLE promotion (
            id INTEGER PRIMARY KEY,
            listing_id INTEGER, kind TEXT, descr TEXT, value INTEGER, threshold INTEGER
        );
        CREATE TABLE delivery (
            platform TEXT PRIMARY KEY, base_fee INTEGER, free_over INTEGER
        );
        """
    )

    for platform, base_fee, free_over in seed_data.DELIVERY:
        cur.execute("INSERT INTO delivery VALUES (?,?,?)", (platform, base_fee, free_over))

    for row in seed_data.LISTINGS:
        cur.execute(
            "INSERT INTO listing"
            " (platform,merchant,brand,name,spec,type,barcode,list_price,sale_price)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (row["platform"], row["merchant"], row["brand"], row["name"], row["spec"],
             row["type"], row["barcode"], row["list_price"], row["sale_price"]),
        )
        listing_id = cur.lastrowid
        for kind, desc, value, threshold in row.get("promotions", []):
            cur.execute(
                "INSERT INTO promotion (listing_id,kind,descr,value,threshold) VALUES (?,?,?,?,?)",
                (listing_id, kind, desc, value, threshold),
            )
    conn.commit()
    return conn


def load_listings(conn: sqlite3.Connection, platform: str) -> list[Listing]:
    """读取某平台的全部条目（含优惠）。"""
    cur = conn.cursor()
    listings: list[Listing] = []
    for r in cur.execute("SELECT * FROM listing WHERE platform=?", (platform,)).fetchall():
        promos = [
            Promotion(kind=p["kind"], desc=p["descr"], value=p["value"], threshold=p["threshold"])
            for p in cur.execute(
                "SELECT * FROM promotion WHERE listing_id=?", (r["id"],)
            ).fetchall()
        ]
        listings.append(
            Listing(
                platform=r["platform"], merchant=r["merchant"], brand=r["brand"],
                name=r["name"], spec=r["spec"], type=r["type"],
                list_price=r["list_price"], sale_price=r["sale_price"],
                barcode=r["barcode"], promotions=promos,
            )
        )
    return listings


def load_delivery(conn: sqlite3.Connection, platform: str) -> DeliveryPolicy:
    r = conn.execute("SELECT * FROM delivery WHERE platform=?", (platform,)).fetchone()
    return DeliveryPolicy(platform=platform, base_fee=r["base_fee"], free_over=r["free_over"])
