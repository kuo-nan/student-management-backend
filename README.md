# 学生管理后台系统

[![CI](https://github.com/kuo-nan/student-management-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/kuo-nan/student-management-backend/actions/workflows/ci.yml)

基于 FastAPI、SQLAlchemy 2 和 MySQL 实现的学生管理后台，覆盖学生、教师、课程、选课、考试、成绩、请假和操作日志等业务。

项目使用 Docker Compose 同时运行 FastAPI、MySQL 和 Redis，包含数据库迁移、自动化测试、Redis 故障降级、容器健康检查和本地演示数据。

## 核心能力

- JWT 登录鉴权与 bcrypt 密码哈希
- 管理员和学生两类角色
- `User -> Student` 一对一身份绑定
- 管理员管理接口、学生本人数据接口分离
- 学号唯一约束与应用层级联校验
- 课程名、班级名唯一约束及并发冲突处理
- 选课重复校验与数据库联合主键保障
- 请假审批条件更新，防止并发重复审批
- ExamScore、课程成绩与学生个人评分职责分离
- Excel 批量导入及行级错误反馈
- Redis 登录限流与统计缓存，故障时自动降级
- 每日滚动日志与操作审计日志
- Alembic 数据库版本管理
- pytest 自动化测试与真实 MySQL 并发测试
- Docker Compose 一键启动 MySQL、Redis 和应用

## 系统架构

```mermaid
flowchart LR
    Client[Swagger / HTTP Client] --> FastAPI[FastAPI Application]
    FastAPI --> Auth[JWT Authentication]
    FastAPI --> Router[Router Layer]
    Router --> Service[Service Layer]
    Service --> ORM[SQLAlchemy 2 ORM]
    ORM --> MySQL[(MySQL 8)]
    FastAPI --> Redis[(Redis)]
    Alembic[Alembic] --> MySQL
    Pytest[pytest / Ruff] --> FastAPI
```

应用容器通过 Docker 内部网络访问 `mysql:3306` 和 `redis:6379`。MySQL 与 Redis 不映射宿主机公网端口。

## 数据库关系

```mermaid
erDiagram
    User ||--o| Student : binds
    Dept ||--o{ Student : contains
    Student ||--o{ StudentLeave : submits
    Student ||--o{ StudentCourse : enrolls
    Course ||--o{ StudentCourse : includes
    Teacher ||--o{ TeacherCourse : teaches
    Course ||--o{ TeacherCourse : assigned
    Student ||--o{ ExamScore : receives
    Exam ||--o{ ExamScore : contains
    Course ||--o{ ExamScore : targets

    StudentCourse {
        int student_id PK
        int course_id PK
        int score
    }
    TeacherCourse {
        int teacher_id PK
        int course_id PK
    }
```

## 核心业务设计

| 链路 | 关键设计 |
| --- | --- |
| 登录与鉴权 | JWT、bcrypt、账号禁用检查、Redis 登录限流 |
| 学生本人数据 | 通过 `Student.user_id` 绑定身份，不假定两表主键相同 |
| 选课 | 联合主键防止重复，捕获并发 `IntegrityError` |
| 请假审批 | 条件更新 `WHERE status = pending`，防止重复审批 |
| 学生新增 | 学号唯一约束，应用层检查和并发冲突回滚 |
| 课程与班级 | 名称唯一约束，应用层预检查并捕获并发 `IntegrityError` |
| 数据迁移 | Alembic 支持空库建表、旧数据检查和字段重命名 |
| Redis 降级 | 限流与缓存故障时回退到数据库或跳过辅助检查 |

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
| CI | GitHub Actions |

## 权限设计

| 接口类型 | 访问身份 |
| --- | --- |
| 健康检查、登录、注册 | 公开 |
| 我的信息、修改密码 | 已登录用户 |
| 我的请假、我的考试成绩 | 已绑定学生账号 |
| 学生、教师、课程、班级管理 | 管理员 |
| 选课、成绩录入、统计、导入、日志 | 管理员 |

管理员可以通过 `POST /auth/user/student_account` 为学生创建并绑定登录账号。

## Docker 快速启动

环境要求：Docker Desktop、WSL2。

```powershell
Copy-Item .env.example .env
```

修改 `.env` 中的：

```dotenv
MYSQL_ROOT_PASSWORD=设置一个强密码
JWT_SECRET=设置一个至少32位的随机密钥
```

启动：

```powershell
docker compose up -d --build
docker compose ps
```

三个容器都应显示 `healthy`：

```text
fastapiproject2-app-1
fastapiproject2-mysql-1
fastapiproject2-redis-1
```

初始化演示数据：

```powershell
docker compose exec app python -m scripts.seed
```

访问：

- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

种子脚本会创建本地演示管理员。若没有通过 `--admin-password` 或 `SEED_ADMIN_PASSWORD` 指定密码，会随机生成并打印一次。演示学生账号为 `student / student12345`，仅用于本地开发。

完整的服务器、Nginx、HTTPS 与备份步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 本地开发

环境要求：

- Python 3.12
- MySQL 8
- Redis 可选；未启动时登录限流和统计缓存自动降级

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

创建数据库：

```sql
CREATE DATABASE student1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

执行迁移并启动：

```powershell
alembic upgrade head
python -m scripts.seed
uvicorn main:app --reload
```

## 测试与代码检查

```powershell
pytest
ruff check .
```

当前有 20 个默认 API 测试，另有 4 个真实 MySQL 并发测试需要单独配置测试数据库；实际覆盖率以 pytest 输出为准。

真实 MySQL 并发测试使用独立临时数据库。测试会删除并重建目标库的数据表，数据库名必须包含 `test` 或 `verify`：

```powershell
$env:MYSQL_TEST_DATABASE_URL = "mysql+pymysql://root:password@127.0.0.1:3306/fastapi_concurrency_test?charset=utf8mb4"
pytest tests/test_mysql_concurrency.py
```

不要指向 `student1`。

## 成绩定义

- `student.personal_score`：学生个人评分，与课程和考试无关。
- `student_course.score`：学生某门课程的最终课程成绩。
- `exam_score.exam_score`：某次考试、某门课程的单次考试成绩。

目前课程成绩和考试成绩不会自动转换为学生个人评分。

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
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## 演示与求职材料

- [三分钟项目演示脚本](DEMO.md)
- [简历项目描述参考](RESUME_BULLETS.md)

## 已知限制

- 课程最终成绩与考试明细之间的权重和换算规则尚未实现。
- 文件当前保存到本地磁盘或 Docker Volume，生产环境应迁移到对象存储。
- 暂不租用公网服务器，项目通过本地 Docker 环境和演示视频展示。
