-- WISHLY 2.0: voer dit volledig uit in Supabase SQL Editor (nieuw project).
-- Auth -> Providers -> Email activeren. E-mailbevestiging aanbevolen.
create extension if not exists pgcrypto;

create table if not exists public.wishly_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  share_token uuid not null unique default gen_random_uuid(),
  created_at timestamptz not null default now()
);
create table if not exists public.wishly_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 150),
  description text not null default '' check (char_length(description) <= 1500),
  price numeric(12,2) not null check (price >= 0 and price <= 1000000),
  category text not null check (category in ('Tech','Koken','Interieur','Kledij','Varia')),
  shop_url text not null default '' check (shop_url = '' or shop_url ~* '^https?://'),
  image text not null default '' check (image = '' or image ~* '^https://'),
  received boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists wishly_items_user_created on public.wishly_items(user_id,created_at desc);

create table if not exists public.wishly_reservations (
  id uuid primary key default gen_random_uuid(),
  item_id uuid not null unique references public.wishly_items(id) on delete cascade,
  guest_name text not null check (char_length(btrim(guest_name)) between 2 and 80),
  created_at timestamptz not null default now()
);

create or replace function public.wishly_new_profile()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.wishly_profiles(user_id) values (new.id);
  return new;
end; $$;
drop trigger if exists wishly_signup_profile on auth.users;
create trigger wishly_signup_profile after insert on auth.users for each row execute function public.wishly_new_profile();
-- Voor het geval de gebruiker in dit Supabase-project al bestond:
insert into public.wishly_profiles(user_id) select id from auth.users on conflict do nothing;

alter table public.wishly_profiles enable row level security;
alter table public.wishly_items enable row level security;
alter table public.wishly_reservations enable row level security;
revoke all on table public.wishly_profiles, public.wishly_items, public.wishly_reservations from anon, authenticated;
grant select on public.wishly_profiles to authenticated;
grant select,insert,update,delete on public.wishly_items to authenticated;

create policy wishly_profile_owner_read on public.wishly_profiles for select to authenticated using ((select auth.uid()) = user_id);
create policy wishly_item_owner_read on public.wishly_items for select to authenticated using ((select auth.uid()) = user_id);
create policy wishly_item_owner_add on public.wishly_items for insert to authenticated with check ((select auth.uid()) = user_id);
create policy wishly_item_owner_update on public.wishly_items for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy wishly_item_owner_delete on public.wishly_items for delete to authenticated using ((select auth.uid()) = user_id);
-- GEEN RLS-policies of tabelrechten op reserveringen: ook de eigenaar kan geen namen of reserveringen opvragen.

-- Publieke bezoekers krijgen uitsluitend deze gegevens, nooit namen of gebruikersgegevens.
create or replace function public.wishly_public_items(p_token uuid)
returns jsonb language sql security definer stable set search_path = '' as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', i.id, 'title', i.title, 'description', i.description, 'price', i.price,
    'category', i.category, 'shop_url', i.shop_url, 'image', i.image,
    'received', i.received, 'reserved', (r.item_id is not null),
    'created_at', i.created_at
  ) order by i.created_at desc), '[]'::jsonb)
  from public.wishly_profiles p
  join public.wishly_items i on i.user_id=p.user_id
  left join public.wishly_reservations r on r.item_id=i.id
  where p.share_token=p_token;
$$;

-- Eén cadeau maximaal één reservering; UNIQUE index beslist atomair bij gelijktijdige bezoekers.
create or replace function public.wishly_reserve(p_token uuid, p_item uuid, p_name text)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if p_name is null or char_length(btrim(p_name)) not between 2 and 80 then
    raise exception 'Vul je naam in (2 tot 80 tekens).';
  end if;
  if not exists (
    select 1 from public.wishly_items i
    join public.wishly_profiles p on p.user_id=i.user_id
    where p.share_token=p_token and i.id=p_item and not i.received
  ) then
    raise exception 'Dit cadeau is niet beschikbaar.';
  end if;
  insert into public.wishly_reservations(item_id,guest_name) values(p_item,btrim(p_name))
  on conflict (item_id) do nothing;
  if not found then
    raise exception 'Dit cadeau is intussen al gereserveerd.';
  end if;
  return true;
end; $$;

-- Functies expliciet beschikbaar, tabellen niet. Alle andere EXECUTE-rechten dicht.
revoke all on function public.wishly_new_profile() from public, anon, authenticated;
revoke all on function public.wishly_public_items(uuid) from public, anon, authenticated;
revoke all on function public.wishly_reserve(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.wishly_public_items(uuid) to anon, authenticated;
grant execute on function public.wishly_reserve(uuid,uuid,text) to anon, authenticated;

-- Foto's kunnen publiek worden bekeken omdat vrienden ze via de lijst nodig hebben.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('wishly-images','wishly-images',true,3145728,array['image/jpeg','image/png','image/webp','image/gif'])
on conflict (id) do update set public=true, file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
drop policy if exists wishly_images_insert on storage.objects;
drop policy if exists wishly_images_delete on storage.objects;
create policy wishly_images_insert on storage.objects for insert to authenticated
with check (bucket_id='wishly-images' and (storage.foldername(name))[1]=(select auth.uid())::text);
create policy wishly_images_delete on storage.objects for delete to authenticated
using (bucket_id='wishly-images' and (storage.foldername(name))[1]=(select auth.uid())::text);
-- Voor download van publieke afbeeldingen is geen select-policy nodig (publieke storage endpoint).

-- Voor nieuwe tabellen: géén impliciete Data API-rechten toekennen.
-- Deze REVOKE/GRANT-instellingen gelden specifiek voor Wishly.
-- Controleer in Supabase Dashboard dat 'Automatically expose new tables' UIT staat.
