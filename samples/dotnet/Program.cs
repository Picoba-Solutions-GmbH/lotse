using LotseDemo.Components;
using Microsoft.AspNetCore.HttpOverrides;

namespace LotseDemo
{
    public class Program
    {
        public static void Main(string[] args)
        {
            var proxyPrefix = Environment.GetEnvironmentVariable("PROXY_PREFIX") ?? "/";

            var builder = WebApplication.CreateBuilder(args);

            // Add services to the container.
            builder.Services.AddRazorComponents()
                .AddInteractiveServerComponents();
            builder.WebHost.UseUrls("http://0.0.0.0:5000");

            var app = builder.Build();
            app.UsePathBase(proxyPrefix);

            // Configure the HTTP request pipeline.
            if (!app.Environment.IsDevelopment())
            {
                app.UseExceptionHandler("/Error");
            }

            app.UseAntiforgery();

            app.MapStaticAssets();
            app.MapRazorComponents<App>()
                .AddInteractiveServerRenderMode();

            app.Run();
        }
    }
}
