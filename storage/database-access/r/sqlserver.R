library(DBI)
library(odbc)
library(rstudioapi)

# If you do not know the port, run this in a terminal:
# tsql -L -H <server-domain>
host <- "<server-domain>"
port <- 1433
database <- "<database>"
user <- "<user>"
password <- askForPassword("Database password")

con <- dbConnect(
  odbc(),
  Driver = "FreeTDS",
  Server = host,
  Port = port,
  Database = database,
  UID = user,
  PWD = password,
  TDS_Version = "7.4"
)

tryCatch({
  dbWriteTable(con, "iris_example", iris, overwrite = TRUE, row.names = FALSE)
  print(head(dbReadTable(con, "iris_example")))
}, finally = {
  dbDisconnect(con)
})
