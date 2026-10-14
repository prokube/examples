# Writes the Iris dataset to Microsoft SQL Server and reads it back.
# Needs an existing SQL Server database that is reachable from this lab.
# Ask your administrator for the connection details, see
# https://prokube.ai/docs/1.9/platform/databases.html#before-you-connect

library(DBI)
library(odbc)
library(rstudioapi)

# If you do not know the port, run this in the RStudio terminal:
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
