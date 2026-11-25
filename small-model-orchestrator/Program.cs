using small_model_orchestrator.Components;
using small_model_orchestrator.Data;
using small_model_orchestrator.Services;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.
builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

var configuredDataDirectory = builder.Configuration["Data:Directory"] ?? "data";
var dataDirectory = Path.GetFullPath(configuredDataDirectory, builder.Environment.ContentRootPath);
Directory.CreateDirectory(dataDirectory);
var databasePath = Path.Combine(dataDirectory, "orchestrator.db");
builder.Services.AddDbContextFactory<OrchestratorDbContext>(options =>
    options.UseSqlite($"Data Source={databasePath}"));
builder.Services.AddScoped<JobRepository>();
builder.Services.AddSingleton<RunQueue>();
builder.Services.AddScoped<JobRunService>();
var executionOptions = builder.Configuration.GetSection("Execution").Get<ExecutionOptions>() ?? new ExecutionOptions();
builder.Services.AddSingleton(executionOptions);
builder.Services.AddSingleton<BashCommandExecutor>();
builder.Services.AddHttpClient<LlamaServerClient>((services, client) =>
{
    var configuration = services.GetRequiredService<IConfiguration>();
    var baseUrl = configuration["LlamaServer:BaseUrl"] ?? "http://127.0.0.1:8080/v1/";
    client.BaseAddress = new Uri(baseUrl.EndsWith('/') ? baseUrl : $"{baseUrl}/");
    client.Timeout = TimeSpan.FromSeconds(configuration.GetValue("LlamaServer:TimeoutSeconds", 600));
});
builder.Services.AddHostedService<JobRunWorker>();

var app = builder.Build();

await using (var scope = app.Services.CreateAsyncScope())
{
    var database = scope.ServiceProvider.GetRequiredService<OrchestratorDbContext>();
    await database.Database.MigrateAsync();
}

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    // The default HSTS value is 30 days. You may want to change this for production scenarios, see https://aka.ms/aspnetcore-hsts.
    app.UseHsts();
}

app.UseHttpsRedirection();

app.UseStaticFiles();
app.UseAntiforgery();

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
