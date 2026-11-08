# 三分钟项目演示脚本

演示前启动服务并初始化数据：

```powershell
docker compose up -d --build
docker compose ps
docker compose exec app python -m scripts.seed
```

准备以下页面：

- Swagger：<http://127.0.0.1:8000/docs>
- GitHub Actions：<https://github.com/kuo-nan/student-management-backend/actions>
- 终端中的 `docker compose ps`

## 0:00-0:20 项目介绍

讲稿：

> 这是一个基于 FastAPI、MySQL 和 Redis 的学生管理后台，包含学生、教师、课程、选课、考试、请假和操作日志。项目重点不只是 CRUD，而是身份绑定、权限隔离、数据库约束、并发处理、迁移和自动化验证。

## 0:20-0:40 Docker 环境

执行：

```powershell
docker compose ps
```

讲稿：

> 应用、MySQL 和 Redis 由 Docker Compose 启动，三个容器都有健康检查。MySQL 和 Redis 只在 Docker 内部网络暴露，应用通过服务名连接，并使用 Volume 持久化数据。

## 0:40-1:05 管理员登录

在 Swagger 执行：

```text
POST /auth/login
```

要点：

- 展示返回的 token 结构即可，不朗读完整 token。
- 点击 Swagger 的 Authorize。
- 调用 `GET /auth/me`。

讲稿：

> 登录时使用 bcrypt 校验密码，通过 JWT 保存用户身份。Redis 对登录频率做限制，Redis 不可用时登录会自动降级。

## 1:05-1:35 学生管理与学号

调用：

```text
POST /student/add_student
GET  /student/list?student_no=20260001
```

再次提交相同学号，展示 409。

讲稿：

> 学号同时受应用层检查和数据库唯一约束保护。两个请求并发创建同一学号时，只有一个能成功，另一个会回滚并返回冲突。

## 1:35-2:05 请假审批

使用学生账号登录：

```text
POST /leave
GET  /leave/my
```

换回管理员账号，调用：

```text
PUT /leave/{leave_id}/audit
```

讲稿：

> 审批使用条件 UPDATE，只允许 pending 状态被修改一次。两个管理员同时审批时，数据库只允许一个请求成功。

## 2:05-2:35 权限隔离

使用学生 token 调用管理员接口：

```text
GET /student/list
```

展示 403。

讲稿：

> 学生账号只能访问自己的请假和考试成绩。用户身份通过 Student.user_id 显式绑定，不依赖两个表主键恰好相同。

## 2:35-3:00 工程验证

展示：

```powershell
pytest
ruff check .
docker compose images
```

再展示 GitHub Actions 成功页面。

讲稿：

> 项目使用 Alembic 管理数据库结构，CI 自动执行代码检查和测试；核心业务流程还包含真实 MySQL 并发测试。

## 录制要求

- 使用 1080p 横屏。
- 隐藏密码、token、浏览器个人账号和桌面隐私信息。
- 鼠标移动要慢，每个接口结果至少停留两秒。
- 视频上传后，将链接补充到 README。
