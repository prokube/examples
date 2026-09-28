library(aws.s3)

bucket <- "<bucketname>"
if (!nzchar(bucket) || bucket == "<bucketname>") {
  stop("Set bucket to your S3 bucket name.", call. = FALSE)
}

key <- "storage-examples/iris.csv"

csv_path <- tempfile(fileext = ".csv")
write.csv(iris, csv_path, row.names = FALSE)

put_object(
  file = csv_path,
  object = key,
  bucket = bucket,
  use_https = FALSE,
  region = ""
)

obj <- get_object(
  object = key,
  bucket = bucket,
  use_https = FALSE,
  region = ""
)

read_back <- read.csv(text = rawToChar(obj))

head(read_back)
