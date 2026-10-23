"""A serving login has no elevated attributes or role-membership paths."""


def safe_reader_role(conn, role=None):
    row = conn.execute(
        "SELECT r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,r.rolreplication,"
        "EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid) AS membership "
        "FROM pg_roles r WHERE r.rolname=COALESCE(%s,current_user)",
        (role,),
    ).fetchone()
    # Reject every membership, including NOINHERIT: SET ROLE can still confer it.
    # A dedicated login receives its SELECT grants directly. PUBLIC is implicit
    # and its effective table/schema permissions are checked by Reader.request.
    return row is not None and not any(row.values())
