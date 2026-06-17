"""Redash から全データを取得して DuckDB キャッシュを更新する。

使い方:
    uv run python update_duckdb.py
"""

import duckdb
import httpx

from kpi import (
    companies,
    company_loyalty,
    contracts,
    customer_lifecycle,
    db,
    feature_health,
    keiei_user_history,
    users,
    work_process_id_generator,
    work_user_history,
)


def main() -> None:
    print("Redash からデータを取得中...")
    with httpx.Client() as client:
        history_df = work_user_history.fetch(client)
        projects_df = work_process_id_generator.fetch(client)
        companies_df = companies.fetch(client)
        contracts_df = contracts.fetch(client)
        users_df = users.fetch(client)
        keiei_history_df = keiei_user_history.fetch(client)

    print("KPI 指標を計算中...")
    conn = duckdb.connect()
    conn.register("work_user_history", history_df)
    conn.register("work_process_id_generator", projects_df)
    conn.register("companies", companies_df)
    conn.register("contracts", contracts_df)
    conn.register("users", users_df)
    conn.register("keiei_user_history", keiei_history_df)

    lifecycle_df = customer_lifecycle.build(conn)
    conn.register("customer_lifecycle", lifecycle_df)

    health_df = feature_health.build(conn)
    conn.register("feature_health", health_df)
    loyalty_df = company_loyalty.build(conn)

    keiei_health_df = feature_health.build_keiei(conn)
    conn.register("keiei_feature_health", keiei_health_df)
    keiei_loyalty_df = company_loyalty.build_keiei(conn)

    conn.close()

    print("DuckDB に保存中...")
    db.save(
        work_user_history=history_df,
        work_process_id_generator=projects_df,
        companies=companies_df,
        contracts=contracts_df,
        users=users_df,
        keiei_user_history=keiei_history_df,
        customer_lifecycle=lifecycle_df,
        feature_health=health_df,
        company_loyalty=loyalty_df,
        keiei_feature_health=keiei_health_df,
        keiei_company_loyalty=keiei_loyalty_df,
    )
    print("完了")


if __name__ == "__main__":
    main()
