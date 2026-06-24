from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Account, AccountSnapshot, FeishuLink, NoteMetrics


class Repository:
    def __init__(self, database_path: str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.database_path)
        self.conn.row_factory = sqlite3.Row

    def migrate(self) -> None:
        self.conn.executescript(
            """
            create table if not exists accounts (
              account_id text primary key,
              account_name text not null,
              operator text not null,
              profile_url text not null,
              niche text,
              stage text,
              notes text
            );

            create table if not exists feishu_links (
              message_id text primary key,
              sender_name text not null,
              sent_at text not null,
              url text not null unique
            );

            create table if not exists note_metrics (
              note_id text primary key,
              url text not null,
              account_id text,
              title text,
              body text,
              published_at text,
              likes integer not null default 0,
              collects integer not null default 0,
              comments integer not null default 0,
              shares integer not null default 0,
              views integer not null default 0,
              leads integer not null default 0,
              captured_at text not null
            );

            create table if not exists note_metric_snapshots (
              snapshot_id integer primary key autoincrement,
              note_id text not null,
              url text not null,
              account_id text,
              title text,
              body text,
              published_at text,
              likes integer not null default 0,
              collects integer not null default 0,
              comments integer not null default 0,
              shares integer not null default 0,
              views integer not null default 0,
              leads integer not null default 0,
              captured_at text not null
            );

            create index if not exists idx_note_metric_snapshots_note_time
              on note_metric_snapshots(note_id, captured_at);

            create index if not exists idx_note_metric_snapshots_time
              on note_metric_snapshots(captured_at);

            create table if not exists account_snapshots (
              account_id text not null,
              captured_at text not null,
              followers integer not null default 0,
              following integer not null default 0,
              liked_and_collected integer not null default 0,
              notes_count integer not null default 0,
              leads integer not null default 0,
              primary key (account_id, captured_at)
            );

            create table if not exists image_jobs (
              job_id integer primary key autoincrement,
              note_id text not null,
              target_account text not null,
              prompt text not null,
              status text not null default 'pending',
              provider text,
              model text,
              error text,
              created_at text not null,
              updated_at text not null
            );

            create table if not exists generated_images (
              image_id integer primary key autoincrement,
              job_id integer not null,
              note_id text not null,
              target_account text not null,
              prompt text not null,
              image_url text,
              image_path text,
              created_at text not null
            );

            create index if not exists idx_image_jobs_status
              on image_jobs(status, created_at);

            create table if not exists model_call_logs (
              log_id integer primary key autoincrement,
              task_type text not null,
              provider text not null,
              model text not null,
              input_tokens integer not null default 0,
              output_tokens integer not null default 0,
              total_tokens integer not null default 0,
              estimated_cost_usd real not null default 0,
              status text not null,
              error text,
              created_at text not null
            );

            create index if not exists idx_model_call_logs_created_at
              on model_call_logs(created_at);

            create table if not exists intake_orders (
              order_id text primary key,
              source text not null,
              school text,
              major text,
              service_type text,
              ddl text,
              student_pain text,
              budget text,
              sales_owner text,
              raw_payload text,
              created_at text not null,
              updated_at text not null
            );

            create table if not exists review_items (
              review_id integer primary key autoincrement,
              source_type text not null,
              source_id text not null,
              title text not null,
              summary text not null,
              recommended_account text,
              risk_level text not null,
              status text not null default 'pending_review',
              reviewer text,
              review_comment text,
              created_at text not null,
              updated_at text not null
            );

            create index if not exists idx_review_items_status
              on review_items(status, created_at);
            """
        )
        self.conn.commit()

    def upsert_accounts(self, accounts: list[Account]) -> None:
        self.conn.executemany(
            """
            insert into accounts values (?, ?, ?, ?, ?, ?, ?)
            on conflict(account_id) do update set
              account_name=excluded.account_name,
              operator=excluded.operator,
              profile_url=excluded.profile_url,
              niche=excluded.niche,
              stage=excluded.stage,
              notes=excluded.notes
            """,
            [
                (
                    a.account_id,
                    a.account_name,
                    a.operator,
                    a.profile_url,
                    a.niche,
                    a.stage,
                    a.notes,
                )
                for a in accounts
            ],
        )
        self.conn.commit()

    def add_links(self, links: list[FeishuLink]) -> int:
        before = self.conn.total_changes
        self.conn.executemany(
            """
            insert or ignore into feishu_links(message_id, sender_name, sent_at, url)
            values (?, ?, ?, ?)
            """,
            [(l.message_id, l.sender_name, l.sent_at.isoformat(), l.url) for l in links],
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def uncollected_links(self) -> list[str]:
        rows = self.conn.execute(
            """
            select fl.url
            from feishu_links fl
            left join note_metrics nm on nm.url = fl.url
            where nm.url is null
            order by fl.sent_at asc
            """
        ).fetchall()
        return [r["url"] for r in rows]

    def known_note_urls(self) -> list[str]:
        rows = self.conn.execute(
            """
            select url from note_metrics
            union
            select url from feishu_links
            order by url
            """
        ).fetchall()
        return [r["url"] for r in rows]

    def urls_without_browser_data(self) -> list[str]:
        rows = self.conn.execute(
            """
            select fl.url
            from feishu_links fl
            left join note_metrics nm on nm.url = fl.url
            where nm.url is null
               or nm.title is null
               or nm.title = ''
               or nm.title = '待抓取标题'
               or nm.body is null
               or nm.body = ''
               or nm.body like '%占位数据%'
            order by fl.sent_at asc
            """
        ).fetchall()
        return [r["url"] for r in rows]

    def urls_for_report_date(self, report_date) -> list[str]:
        rows = self.conn.execute(
            """
            select distinct url
            from note_metrics
            where substr(coalesce(published_at, captured_at), 1, 10) = ?
              and title is not null
              and title != ''
              and title != '待抓取标题'
            order by url
            """,
            (report_date.isoformat(),),
        ).fetchall()
        return [r["url"] for r in rows]

    def upsert_note_metrics(self, notes: list[NoteMetrics]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.executemany(
            """
            insert into note_metrics values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(note_id) do update set
              url=excluded.url,
              account_id=excluded.account_id,
              title=excluded.title,
              body=excluded.body,
              published_at=excluded.published_at,
              likes=excluded.likes,
              collects=excluded.collects,
              comments=excluded.comments,
              shares=excluded.shares,
              views=excluded.views,
              leads=excluded.leads,
              captured_at=excluded.captured_at
            """,
            [
                (
                    n.note_id,
                    n.url,
                    n.account_id,
                    n.title,
                    n.body,
                    n.published_at.isoformat() if n.published_at else None,
                    n.likes,
                    n.collects,
                    n.comments,
                    n.shares,
                    n.views,
                    n.leads,
                    now,
                )
                for n in notes
            ],
        )
        self.conn.executemany(
            """
            insert into note_metric_snapshots(
              note_id, url, account_id, title, body, published_at,
              likes, collects, comments, shares, views, leads, captured_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    n.note_id,
                    n.url,
                    n.account_id,
                    n.title,
                    n.body,
                    n.published_at.isoformat() if n.published_at else None,
                    n.likes,
                    n.collects,
                    n.comments,
                    n.shares,
                    n.views,
                    n.leads,
                    now,
                )
                for n in notes
            ],
        )
        self.conn.commit()

    def add_account_snapshots(self, snapshots: list[AccountSnapshot]) -> None:
        self.conn.executemany(
            """
            insert or replace into account_snapshots values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    s.account_id,
                    s.captured_at.isoformat(),
                    s.followers,
                    s.following,
                    s.liked_and_collected,
                    s.notes_count,
                    s.leads,
                )
                for s in snapshots
            ],
        )
        self.conn.commit()

    def add_image_job(self, note_id: str, target_account: str, prompt: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            """
            insert into image_jobs(note_id, target_account, prompt, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            """,
            (note_id, target_account, prompt, now, now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def pending_image_jobs(self, limit: int | None = None) -> list[sqlite3.Row]:
        sql = """
            select *
            from image_jobs
            where status = 'pending'
            order by created_at asc
        """
        params: tuple = ()
        if limit:
            sql += " limit ?"
            params = (limit,)
        return self.conn.execute(sql, params).fetchall()

    def mark_image_job_running(self, job_id: int, provider: str, model: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            update image_jobs
            set status = 'running', provider = ?, model = ?, error = null, updated_at = ?
            where job_id = ?
            """,
            (provider, model, now, job_id),
        )
        self.conn.commit()

    def mark_image_job_failed(self, job_id: int, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            update image_jobs
            set status = 'failed', error = ?, updated_at = ?
            where job_id = ?
            """,
            (error[:1000], now, job_id),
        )
        self.conn.commit()

    def add_generated_image(
        self,
        job_id: int,
        note_id: str,
        target_account: str,
        prompt: str,
        image_url: str = "",
        image_path: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            insert into generated_images(job_id, note_id, target_account, prompt, image_url, image_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, note_id, target_account, prompt, image_url, image_path, now),
        )
        self.conn.execute(
            """
            update image_jobs
            set status = 'completed', updated_at = ?
            where job_id = ?
            """,
            (now, job_id),
        )
        self.conn.commit()

    def add_model_call_log(
        self,
        task_type: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float,
        status: str,
        error: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            insert into model_call_logs(
              task_type, provider, model, input_tokens, output_tokens,
              total_tokens, estimated_cost_usd, status, error, created_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_type,
                provider,
                model,
                input_tokens,
                output_tokens,
                total_tokens,
                estimated_cost_usd,
                status,
                error[:1000],
                now,
            ),
        )
        self.conn.commit()

    def add_intake_order(self, payload: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        order_id = str(payload.get("order_id") or f"ORD-{int(datetime.now().timestamp())}")
        self.conn.execute(
            """
            insert into intake_orders(
              order_id, source, school, major, service_type, ddl,
              student_pain, budget, sales_owner, raw_payload, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(order_id) do update set
              source=excluded.source,
              school=excluded.school,
              major=excluded.major,
              service_type=excluded.service_type,
              ddl=excluded.ddl,
              student_pain=excluded.student_pain,
              budget=excluded.budget,
              sales_owner=excluded.sales_owner,
              raw_payload=excluded.raw_payload,
              updated_at=excluded.updated_at
            """,
            (
                order_id,
                str(payload.get("source") or "sales_pool"),
                str(payload.get("school") or ""),
                str(payload.get("major") or ""),
                str(payload.get("service_type") or ""),
                str(payload.get("ddl") or ""),
                str(payload.get("student_pain") or ""),
                str(payload.get("budget") or ""),
                str(payload.get("sales_owner") or ""),
                str(payload),
                now,
                now,
            ),
        )
        self.conn.execute("delete from review_items where source_type = 'order' and source_id = ?", (order_id,))
        analysis = _order_review_analysis(payload)
        cursor = self.conn.execute(
            """
            insert into review_items(
              source_type, source_id, title, summary, recommended_account,
              risk_level, status, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)
            """,
            (
                "order",
                order_id,
                analysis["title"],
                analysis["summary"],
                analysis["recommended_account"],
                analysis["risk_level"],
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_review(self, review_id: int, reviewer: str, decision: str, comment: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        if decision not in {"approved", "rejected", "needs_edit", "pending_review"}:
            raise ValueError("decision must be approved, rejected, needs_edit, or pending_review")
        self.conn.execute(
            """
            update review_items
            set status = ?, reviewer = ?, review_comment = ?, updated_at = ?
            where review_id = ?
            """,
            (decision, reviewer, comment[:1000], now, review_id),
        )
        self.conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()


def _order_review_analysis(payload: dict) -> dict:
    service = str(payload.get("service_type") or "课业服务")
    school = str(payload.get("school") or "未知学校")
    major = str(payload.get("major") or "未知专业")
    pain = str(payload.get("student_pain") or "学生需求待补充")
    ddl = str(payload.get("ddl") or "DDL 待确认")
    text = f"{service} {pain} {ddl}".lower()
    if any(word in text for word in ("48", "urgent", "今晚", "明天", "挂科", "appeal")):
        risk_level = "high"
    elif any(word in text for word in ("3-7", "turnitin", "ai", "查重", "proposal")):
        risk_level = "medium"
    else:
        risk_level = "low"
    if any(word in text for word in ("appeal", "挂科", "final", "quiz", "考试")):
        account = "考试/挂科补救业务号"
    elif any(word in text for word in ("turnitin", "ai", "案例", "查重")):
        account = "案例/转化业务号"
    else:
        account = "论文/作业业务号"
    return {
        "title": f"{school} {major}｜{service}",
        "summary": f"痛点：{pain}；DDL：{ddl}。建议先生成小红书内容结构，再进入图片任务，最后由人工审核后使用。",
        "recommended_account": account,
        "risk_level": risk_level,
    }
