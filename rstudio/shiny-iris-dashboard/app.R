library(shiny)
library(ggplot2)
library(dplyr)

# The Iris dataset ships with R, which keeps this example runnable without
# downloads, credentials, or access to external services.
iris_df <- as_tibble(iris)
numeric_columns <- c("Sepal.Length", "Sepal.Width", "Petal.Length", "Petal.Width")
species_levels <- levels(iris_df$Species)

# Simple in-memory classifier used to keep the app self-contained.
# Each species is represented by the average of its numeric measurements.
species_centroids <- iris_df %>%
  group_by(Species) %>%
  summarise(across(all_of(numeric_columns), mean), .groups = "drop")

# The UI defines the controls and output placeholders. Shiny automatically
# connects these input and output IDs to the server logic below.
ui <- fluidPage(
  titlePanel("Shiny Iris Explorer"),
  p(
    "An interactive RStudio/Shiny dashboard for exploring the built-in Iris dataset, ",
    "filtering records, inspecting plots, and trying a lightweight species prediction."
  ),
  sidebarLayout(
    sidebarPanel(
      # These controls demonstrate reactive inputs: changing any of them
      # invalidates dependent calculations and refreshes the affected outputs.
      checkboxGroupInput(
        inputId = "species",
        label = "Species",
        choices = species_levels,
        selected = species_levels
      ),
      sliderInput(
        inputId = "petal_length",
        label = "Petal length range",
        min = min(iris_df$Petal.Length),
        max = max(iris_df$Petal.Length),
        value = range(iris_df$Petal.Length),
        step = 0.1
      ),
      sliderInput(
        inputId = "sepal_length",
        label = "Sepal length range",
        min = min(iris_df$Sepal.Length),
        max = max(iris_df$Sepal.Length),
        value = range(iris_df$Sepal.Length),
        step = 0.1
      ),
      selectInput(
        inputId = "x_var",
        label = "X axis",
        choices = numeric_columns,
        selected = "Petal.Length"
      ),
      selectInput(
        inputId = "y_var",
        label = "Y axis",
        choices = numeric_columns,
        selected = "Petal.Width"
      ),
      checkboxInput(
        inputId = "show_trend",
        label = "Show trend line",
        value = TRUE
      )
    ),
    mainPanel(
      tabsetPanel(
        tabPanel(
          "Explore",
          br(),
          # Outputs are placeholders. Their contents are produced in the
          # matching render* calls in the server function.
          plotOutput("scatter_plot", height = "460px"),
          h4("Filtered summary"),
          verbatimTextOutput("summary_text")
        ),
        tabPanel(
          "Data",
          br(),
          downloadButton("download_filtered", "Download filtered CSV"),
          br(),
          br(),
          dataTableOutput("iris_table")
        ),
        tabPanel(
          "Predict",
          br(),
          p("Adjust the flower measurements to classify the observation using nearest species centroids."),
          fluidRow(
            column(3, numericInput("predict_sepal_length", "Sepal length", value = 5.1, min = 0, step = 0.1)),
            column(3, numericInput("predict_sepal_width", "Sepal width", value = 3.5, min = 0, step = 0.1)),
            column(3, numericInput("predict_petal_length", "Petal length", value = 1.4, min = 0, step = 0.1)),
            column(3, numericInput("predict_petal_width", "Petal width", value = 0.2, min = 0, step = 0.1))
          ),
          h4(textOutput("prediction_text")),
          plotOutput("prediction_plot", height = "380px")
        )
      )
    )
  )
)

server <- function(input, output, session) {
  # A reactive expression stores shared filtering logic. Any output that calls
  # filtered_iris() will update automatically when the selected inputs change.
  filtered_iris <- reactive({
    validate(need(length(input$species) > 0, "Select at least one species."))

    iris_df %>%
      filter(
        Species %in% input$species,
        between(Petal.Length, input$petal_length[1], input$petal_length[2]),
        between(Sepal.Length, input$sepal_length[1], input$sepal_length[2])
      )
  })

  output$scatter_plot <- renderPlot({
    plot_data <- filtered_iris()
    validate(need(nrow(plot_data) > 0, "No rows match the selected filters."))

    # The selected column names are read from input$x_var and input$y_var.
    # .data[[...]] lets ggplot use those dynamic column names safely.
    plot <- ggplot(plot_data, aes(x = .data[[input$x_var]], y = .data[[input$y_var]], color = Species)) +
      geom_point(size = 3, alpha = 0.75) +
      labs(
        title = "Interactive Iris feature comparison",
        subtitle = paste(nrow(plot_data), "rows currently selected"),
        x = input$x_var,
        y = input$y_var
      ) +
      theme_minimal(base_size = 13)

    # The trend line is optional so users can see how a checkbox changes the
    # rendered chart without changing the underlying data.
    if (isTRUE(input$show_trend) && nrow(plot_data) > 2) {
      plot <- plot + geom_smooth(method = "lm", se = FALSE, linewidth = 0.8)
    }

    plot
  })

  output$summary_text <- renderPrint({
    plot_data <- filtered_iris()
    validate(need(nrow(plot_data) > 0, "No rows match the selected filters."))

    # This summary is recalculated for the currently filtered rows only.
    plot_data %>%
      group_by(Species) %>%
      summarise(
        rows = n(),
        across(all_of(numeric_columns), ~ round(mean(.x), 2), .names = "mean_{.col}"),
        .groups = "drop"
      )
  })

  output$iris_table <- renderDataTable({
    filtered_iris()
  }, options = list(pageLength = 10, scrollX = TRUE))

  # downloadHandler receives the same reactive data as the plot and table, so
  # the downloaded file always matches the user's current filter state.
  output$download_filtered <- downloadHandler(
    filename = function() {
      paste0("filtered-iris-", Sys.Date(), ".csv")
    },
    content = function(file) {
      write.csv(filtered_iris(), file, row.names = FALSE)
    }
  )

  # Collect the four numeric prediction inputs into one named vector. The names
  # match numeric_columns, which keeps the distance calculation straightforward.
  prediction_values <- reactive({
    c(
      Sepal.Length = input$predict_sepal_length,
      Sepal.Width = input$predict_sepal_width,
      Petal.Length = input$predict_petal_length,
      Petal.Width = input$predict_petal_width
    )
  })

  predicted_species <- reactive({
    values <- prediction_values()
    centroid_matrix <- as.matrix(species_centroids[, numeric_columns])

    # Classify the input by finding the closest species centroid in feature
    # space. This is intentionally simple and transparent for demonstration.
    distances <- apply(centroid_matrix, 1, function(row) sqrt(sum((row - values) ^ 2)))

    species_centroids$Species[which.min(distances)]
  })

  output$prediction_text <- renderText({
    paste("Predicted species:", predicted_species())
  })

  output$prediction_plot <- renderPlot({
    # The input point is plotted alongside the original data and species
    # centroids so users can see why the nearest-centroid prediction changed.
    input_point <- tibble(
      Sepal.Length = input$predict_sepal_length,
      Sepal.Width = input$predict_sepal_width,
      Petal.Length = input$predict_petal_length,
      Petal.Width = input$predict_petal_width,
      Species = predicted_species()
    )

    ggplot(iris_df, aes(x = Petal.Length, y = Petal.Width, color = Species)) +
      geom_point(alpha = 0.35) +
      geom_point(data = species_centroids, shape = 4, size = 5, stroke = 1.5) +
      geom_point(data = input_point, shape = 8, size = 6, stroke = 1.5) +
      labs(
        title = "Prediction compared with Iris observations",
        subtitle = "Crosses are species centroids; the star is the measurement being classified.",
        x = "Petal length",
        y = "Petal width"
      ) +
      theme_minimal(base_size = 13)
  })
}

shinyApp(ui = ui, server = server)
