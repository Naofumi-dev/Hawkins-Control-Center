# Supabase database CA certificate

`supabase-ca.crt` is a **public root certificate**, not a credential or private key. It was downloaded on 2026-10-05 using **Database → Settings → SSL configuration → Download certificate** in the owned Hawkins project `mtdavgadkiiofwikzdtn`.

- Subject/issuer: Supabase Root 2021 CA, Supabase Inc.
- Valid until: 2031-04-26 10:56:53 UTC.
- SHA-256 of this PEM file: `700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`.
- Certificate SHA-256 fingerprint: `80:70:25:AD:50:D4:ED:21:9D:2C:9C:7D:29:9C:00:4F:82:4E:B0:0C:F7:F6:5A:FE:F6:07:D0:7B:72:E6:CA:FA`.

The database setup helper pins this file and uses `sslmode=verify-full` against the fixed personal session-pooler host and project user. It does not modify the system trust store or Supabase SSL settings. If Supabase rotates this certificate, obtain the replacement from the authenticated owned project and verify it before updating the pin.

Provider reference: [Connecting with PSQL](https://supabase.com/docs/guides/database/psql).
