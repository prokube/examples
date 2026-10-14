# Writes the Iris dataset to PostgreSQL and reads it back.
# Needs an existing PostgreSQL database that is reachable from this lab.
# Ask your administrator for the connection details, see
# https://prokube.ai/docs/1.9/platform/databases.html#before-you-connect

library(DBI)
library(odbc)
library(rstudioapi)

host <- "<server-domain>"
port <- 5432
database <- "<database>"
user <- "<user>"
password <- askForPassword("Database password")

con <- dbConnect(
  odbc(),
  Driver = "PostgreSQL Unicode",
  Server = host,
  Port = port,
  Database = database,
  UID = user,
  PWD = password
)

tryCatch({
  dbWriteTable(con, "iris_example", iris, overwrite = TRUE, row.names = FALSE)
  print(head(dbReadTable(con, "iris_example")))
}, finally = {
  dbDisconnect(con)
})
