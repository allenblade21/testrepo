# 饮品比价系统 🥤

对 **阿里闪购 / 京东 / 美团** 三个平台上的**饮料饮品**进行到手价比价。搜一款饮品，三平台到手价并排展示，自动标出最便宜方与节省金额。

> 设计文档见 [docs/设计文档.md](docs/设计文档.md)。

## 功能

- **跨平台匹配**：瓶装标品按条码精确匹配；现制饮品按「品牌+品名+规格」归一化匹配（自动吸收 `/`、空格、全角空格等写法差异）
- **到手价引擎**：售价 − 第二件半价/满减/补贴/券 + 配送费，输出透明明细
- **三平台并排比价**：高亮最便宜方、展示节省金额、识别缺货/单边可比、现制饮品起送价校验
- **可插拔适配器**：每平台一个适配器，当前为 Mock（读种子数据），未来接真实数据源只换适配器、上层不动

## 技术栈

Python + FastAPI · SQLite（内置种子数据）· 原生 HTML/JS 前端 · pytest

## 本地运行

```bash
cd beverage-price-comparison
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8077
```

打开浏览器访问 <http://127.0.0.1:8077/>，搜索「可乐 / 农夫山泉 / 元气森林 / 喜茶 / 瑞幸」试试。

## 运行测试

```bash
cd beverage-price-comparison
python -m pytest -q
```

## 接口

| 接口 | 说明 |
| --- | --- |
| `GET /search?q=可乐` | 关键词召回可比饮品 |
| `GET /compare?unit_id=xxx&qty=1&include_delivery=true` | 某饮品三平台到手价对比 |
| `GET /health` | 健康检查 |
| `GET /` | 前端页面 |

FastAPI 自带交互式接口文档：<http://127.0.0.1:8077/docs>

## 目录结构

```
beverage-price-comparison/
├── docs/设计文档.md      设计文档
├── app/
│   ├── main.py           FastAPI 入口 + 比价编排
│   ├── models.py         数据模型
│   ├── db.py             SQLite + 种子数据
│   ├── matching.py       跨平台匹配引擎
│   ├── pricing.py        到手价计算引擎
│   └── adapters/         平台适配器（阿里闪购/京东/美团，Mock 可插拔）
├── web/index.html        前端页面
├── tests/                pytest（匹配 + 算价 + 接口）
├── seed_data.py          Mock 种子数据
└── requirements.txt
```

## 数据说明

当前使用 **Mock 种子数据**（演示用，非真实价格），目的是让全流程在沙盒/本地即可运行验证。三大平台无公开免费比价接口，接入真实数据需官方授权或合规采集——届时只需替换 `app/adapters/` 下的适配器实现，匹配/算价/比价/展示逻辑无需改动。
