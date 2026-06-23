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

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()
