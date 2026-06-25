# Connecting to a SQL Server Named Instance with FreeTDS

## What is a Named Instance?

A single machine can run **multiple SQL Server installations** side by side.
Each installation is called an **instance**:

| Type | Example | Default Port |
|---|---|---|
| **Default instance** | `myserver.example.com` | **1433** (always) |
| **Named instance** | `myserver.example.com\PROD` | **Dynamic** (assigned at startup) |

The `\PROD` part after the hostname is the **instance name**. It is **not** part of
the hostname or domain — it tells the SQL Server Browser service which installation
on that machine you want to reach.

> **Key point:** A named instance does not listen on port 1433. It gets a
> dynamically assigned port each time it starts, unless a DBA has pinned it to a
> fixed port.

---

## The Problem with FreeTDS

**FreeTDS does not support the `hostname\INSTANCE` syntax.** Unlike the Microsoft
ODBC Driver, FreeTDS cannot resolve a named instance to its TCP port automatically.

This means you **must first discover the correct TCP port** of the named instance
yourself, and then use that port directly in your driver configuration.

---

## Step 1 — Find the TCP Port of the Named Instance

Open a **Terminal** in RStudio (*Tools > Terminal > New Terminal*) and run:

```bash
tsql -L mysql.prod.customer.tld
```

This queries the SQL Server Browser service and lists all instances on that host.
Example output:

```
ServerName MySQL
InstanceName PROD
IsClustered No
Version 14.0.3456.2
tcp 51433
```

Find the entry for your instance (`PROD`) and note the value of the **`tcp`
attribute** — this is the TCP port the instance is listening on. In this example,
the port is **51433**.

> If the Browser service (UDP 1434) is blocked by a firewall, `tsql -L` will time
> out. In that case, contact your DBA to provide the port.

---

## Step 2 — Use the Port in Your Connection

Take the `tcp` value from Step 1 and use it as the `Port` in `dbConnect()`:

```r
library(DBI)
library(odbc)
library(rstudioapi)

# --- Connection to named instance PROD (tcp port from Step 1) ---
con <- dbConnect(
  odbc::odbc(),
  Driver      = "FreeTDS",
  Server      = "mysql.prod.customer.tld",   # hostname only — do NOT add \PROD
  Port        = 51433,                                # tcp value from tsql -L output
  Database    = "your_database",
  UID         = "your_user",
  PWD         = askForPassword(prompt = "Please enter your password:"),
  TDS_Version = "7.4"                                 # use 7.4 for SQL Server 2017
)

# --- Query ---
result <- dbGetQuery(con, "SELECT TOP 10 * FROM your_table")
print(result)

# --- Disconnect ---
dbDisconnect(con)
```
