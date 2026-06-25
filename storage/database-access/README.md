# Database Access

These examples show how to connect from the pk notebook and pk RStudio images to common relational databases.

The pk notebook and pk RStudio images already include the required ODBC drivers and language packages. Each example uses the Iris dataset, creates a table named `iris_example`, writes the data, reads a few rows back, and closes the connection.

## Examples

- PostgreSQL: `python/postgresql.ipynb`, `r/postgresql.R`
- MariaDB/MySQL: `python/mariadb.ipynb`, `r/mariadb.R`
- Microsoft SQL Server: `python/sqlserver.ipynb`, `r/sqlserver.R`

Edit only the connection values at the top of the example you want to run:

- `host`
- `port`
- `database`
- `user`

The examples prompt for the password.

## Drivers

The Python notebooks use these database drivers:

- PostgreSQL: `psycopg2`
- MariaDB/MySQL: `pyodbc` with `MariaDB Unicode`
- Microsoft SQL Server: `pyodbc` with `FreeTDS`

The R scripts use `DBI` and `odbc` with the same ODBC drivers.

## Microsoft SQL Server

For Microsoft SQL servers you first need to find out which port the server is using. Open a terminal in RStudio and run:

```sh
tsql -L -H <server-domain>
```
