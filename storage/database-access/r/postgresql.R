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
