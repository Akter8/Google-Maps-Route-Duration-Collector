-- Run manually in the Supabase SQL Editor as a project administrator.
-- Replace REPLACE_WITH_A_LONG_RANDOM_PASSWORD before executing. Never commit
-- the resulting URL/password or use the collector's service-role key here.
-- This is intentionally separate so collector schema setup remains unchanged.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'dashboard_reader') then
    create role dashboard_reader login noinherit nosuperuser nocreatedb nocreaterole noreplication
      password 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';
  end if;
end
$$;

-- Rotate/reset the password separately when needed:
-- alter role dashboard_reader password 'REPLACE_WITH_A_NEW_LONG_RANDOM_PASSWORD';

revoke all privileges on database postgres from dashboard_reader;
revoke all privileges on schema public from dashboard_reader;
revoke all privileges on all tables in schema public from dashboard_reader;
revoke all privileges on all sequences in schema public from dashboard_reader;
revoke all privileges on all functions in schema public from dashboard_reader;

grant connect on database postgres to dashboard_reader;
grant usage on schema public to dashboard_reader;
grant select (route_id, direction, date_local, scheduled_slot, duration_seconds,
              static_duration_seconds, api_success, error_message)
  on table public.traffic_observations to dashboard_reader;

-- Assert the intended privileges after running this script.
select has_table_privilege('dashboard_reader', 'public.traffic_observations', 'select') as can_select_observations,
       has_table_privilege('dashboard_reader', 'public.api_usage', 'select') as can_select_api_usage,
       has_table_privilege('dashboard_reader', 'public.traffic_observations', 'insert') as can_insert,
       has_table_privilege('dashboard_reader', 'public.traffic_observations', 'update') as can_update,
       has_table_privilege('dashboard_reader', 'public.traffic_observations', 'delete') as can_delete,
       has_table_privilege('dashboard_reader', 'public.traffic_observations', 'truncate') as can_truncate,
       has_schema_privilege('dashboard_reader', 'public', 'create') as can_create_public_objects;
