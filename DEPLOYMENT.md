# 部署说明

本项目使用 Docker Compose 同时运行 FastAPI、MySQL 和 Redis。生产服务器不要直接暴露 MySQL 和 Redis 端口。

## 服务器要求

- Ubuntu 22.04/24.04 或同类 Linux
- Docker Engine 与 Docker Compose Plugin
- 至少 2 核 CPU、2GB 内存
- 域名和 HTTPS 证书，正式对外访问时必需

## 1. 创建环境文件

在服务器项目根目录创建 `.env`：

```dotenv
APP_PORT=8000
MYSQL_ROOT_PASSWORD=使用强数据库密码
JWT_SECRET=使用至少32位随机密钥
JWT_EXPIRES_MINUTES=1440
WEB_CONCURRENCY=2
```

生成 JWT 密钥可以使用：

```bash
openssl rand -hex 32
```

`.env` 不能提交到 Git。

## 2. 启动服务

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

首次启动会自动执行 Alembic 迁移。MySQL 健康检查通过后，应用才会启动。

创建初始管理员：

```bash
docker compose exec app python -m scripts.seed
```

如果未指定密码，种子脚本会随机生成管理员密码并打印一次。也可以设置：

```bash
export SEED_ADMIN_PASSWORD='使用强管理员密码'
docker compose exec app python -m scripts.seed
```

## 3. 验证

服务器本机检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/docs
```

查看容器健康状态：

```bash
docker compose ps
docker inspect --format='{{json .State.Health}}' "$(docker compose ps -q app)"
```

## 4. 防火墙

公网只开放：

```text
22  SSH
80  HTTP
443 HTTPS
```

不要开放 3306 和 6379。Compose 不为 MySQL 和 Redis 映射宿主机端口，它们只在 Docker 内部网络中可访问。

需要临时连接数据库时使用：

```bash
docker compose exec mysql mysql -uroot -p
docker compose exec redis redis-cli
```

## 5. Nginx 反向代理

应用启动后，Nginx 接收公网请求并转发到 8000：

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

使用 Certbot 或云厂商证书配置 HTTPS：

```bash
sudo certbot --nginx -d api.example.com
```

## 6. 数据备份

备份 MySQL：

```bash
docker compose exec -T mysql sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction student1' \
  > student1_backup.sql
```

定期备份 `mysql_data`、`upload_data` 和 `.env`，并确认备份可以恢复。

## 7. 更新版本

```bash
git pull
docker compose up -d --build
```

更新前先备份数据库。若包含数据库迁移，更新后检查：

```bash
docker compose exec app alembic current
docker compose logs app
```

## 当前部署限制

- 尚未配置 CI/CD 自动部署。
- 文件使用本地 Docker Volume，未接入对象存储。
- 尚未配置集中日志、监控和告警。
- 自动种子数据只适合演示环境，生产环境应使用受控管理员创建流程。
