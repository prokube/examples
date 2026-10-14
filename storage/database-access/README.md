# Database Access

These examples show how to connect from the pk notebook and pk RStudio images to common relational databases.

The pk notebook and pk RStudio images already include the required ODBC drivers and language packages. Each example uses the Iris dataset, creates a table named `iris_example`, writes the data, reads a few rows back, and closes the connection.

## Prerequisites

The PostgreSQL, MariaDB/MySQL, and SQL Server examples connect to an existing database. They do not start one. You need:

- a database that is reachable from your lab;
- its host, port, database name, user, and password.

Ask your administrator which databases are available and for the connection details. See [Platform Databases: Before You Connect](https://prokube.ai/docs/1.9/platform/databases.html#before-you-connect).

## Examples

- PostgreSQL: `python/postgresql.ipynb`, `r/postgresql.R`
- MariaDB/MySQL: `python/mariadb.ipynb`, `r/mariadb.R`
- Microsoft SQL Server: `python/sqlserver.ipynb`, `r/sqlserver.R`
- DuckDB: `python/duckdb.ipynb`

Edit only the connection values at the top of the example you want to run:

- `host`
- `port`
- `database`
- `user`

The examples prompt for the password.

The examples replace the `iris_example` and `iris_example_cursor` tables if they already exist in the target database.

## DuckDB

The DuckDB example does not need a database server. `duckdb.connect()` opens a temporary in-memory database inside the notebook process, and the data is stored as a Parquet file in your S3 bucket. DuckDB is not included in the pk notebook image, so the notebook installs it.

## Drivers

The Python notebooks use these database drivers:

- PostgreSQL: `psycopg2`
- MariaDB/MySQL: `pyodbc` with `MariaDB Unicode`
- Microsoft SQL Server: `pyodbc` with `FreeTDS`

The R scripts use `DBI` and `odbc` with these ODBC drivers:

- PostgreSQL: `PostgreSQL Unicode`
- MariaDB/MySQL: `MariaDB Unicode`
- Microsoft SQL Server: `FreeTDS`

## Microsoft SQL Server

For Microsoft SQL servers you first need to find out which port the server is using. Open a terminal in RStudio or JupyterLab and run:

```sh
tsql -L -H <server-domain>
```

## Troubleshooting

For connection, authentication, and driver errors, see the [troubleshooting table](https://prokube.ai/docs/1.9/platform/databases.html#troubleshooting) in the platform documentation.
