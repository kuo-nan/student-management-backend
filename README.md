# 学生管理后台系统

基于 FastAPI、SQLAlchemy 和 MySQL 实现的学生管理后台，覆盖学生、教师、课程、选课、考试、成绩、请假和操作日志等业务。

## 核心能力

- JWT 登录鉴权与密码哈希存储
- 管理员和学生两类角色
- `User -> Student` 一对一身份绑定
- 管理员管理接口、学生本人数据接口分离
- 选课重复校验与数据库联合主键保障
- 考试名称唯一约束与成绩录入校验
- 请假审批状态流转
- Excel 批量导入及行级错误反馈
- 统一分页、响应格式和异常处理
- Redis 登录限流与统计缓存，故障时自动降级
- 每日滚动日志与操作审计日志
- Alembic 数据库版本管理
- pytest 核心接口测试
- Docker Compose 一键启动 MySQL、Redis 和应用

## 技术栈

| 分类 | 技术 |
| --- | --- |
| Web 框架 | FastAPI |
| 数据校验 | Pydantic |
| ORM | SQLAlchemy 2 |
| 数据库 | MySQL 8 |
| 缓存 | Redis |
| 数据库迁移 | Alembic |
| 密码与令牌 | Passlib、python-jose |
| 测试与检查 | pytest、httpx、Ruff |
| 部署 | Docker、Docker Compose |

## 权限设计

| 接口类型 | 访问身份 |
| --- | --- |
| 健康检查、登录、注册 | 公开 |
| 我的信息、修改密码 | 已登录用户 |
| 我的请假、我的考试成绩 | 已绑定学生账号 |
| 学生、教师、课程、班级管理 | 管理员 |
| 选课、成绩录入、统计、导入、日志 | 管理员 |

管理员可以通过 `POST /auth/user/student_account` 为学生创建并绑定登录账号。学生本人接口通过 `Student.user_id` 查找当前学生，不依赖 `user.id` 与 `student.id` 恰好相同。

## 本地启动

环境要求：

- Python 3.12
- MySQL 8
- Redis 可选；未启动时登录限流和统计缓存会自动降级

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Windows PowerShell 激活命令：

```powershell
.\.venv\Scripts\Activate.ps1
```

修改 `.env` 中的 MySQL 配置，先创建数据库：

```sql
CREATE DATABASE student1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

执行迁移并启动：

```bash
alembic upgrade head
python -m scripts.seed
uvicorn main:app --reload
```

启动后可访问：

- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

`scripts.seed` 会创建本地演示班级和管理员。若没有通过 `--admin-password` 或环境变量 `SEED_ADMIN_PASSWORD` 指定密码，会随机生成并打印一次管理员密码。演示学生账号为 `student / student12345`，只应用于本地开发。

## Docker 启动

```bash
docker compose up --build
```

容器启动时会自动执行 `alembic upgrade head`。生产部署前必须修改 `MYSQL_ROOT_PASSWORD` 和 `JWT_SECRET`。

首次启动后可初始化管理员：

```bash
docker compose exec app python -m scripts.seed
```

## 测试与代码检查

```bash
pytest
ruff check .
```

当前测试覆盖健康检查、未登录拦截、角色权限、学生列表联表返回、学生信息修改、考试权限与重名校验、学生身份绑定、请假归属、成绩录入选课校验和学生账号创建。

## 项目结构

```text
.
├── alembic/                # 数据库迁移
├── routers/                # HTTP 接口层
├── services/               # 核心业务逻辑
├── scripts/seed.py         # 本地初始化数据
├── tests/                  # 自动化测试
├── config.py               # 环境配置
├── database.py             # 数据库与 Redis 连接
├── models.py               # SQLAlchemy 模型
├── schemas.py              # 请求与响应模型
├── main.py                 # 应用入口与全局异常处理
├── Dockerfile
└── docker-compose.yml
```

## 已知限制与后续计划

- 当前同时保留课程平时成绩 `student_course.score` 和考试成绩 `ExamScore.exam_score`，后续需要明确最终成绩计算规则。
- 学生表目前仍使用自增 ID 作为主键，尚未引入独立的学号字段。
- 文件当前保存到本地磁盘，生产环境应迁移到对象存储。
- 在线演示地址和完整接口截图将在部署完成后补充。
