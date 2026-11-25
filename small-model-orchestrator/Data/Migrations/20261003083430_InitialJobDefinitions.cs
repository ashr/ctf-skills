using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace smallmodelorchestrator.Data.Migrations
{
    /// <inheritdoc />
    public partial class InitialJobDefinitions : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "JobDefinitions",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    Name = table.Column<string>(type: "TEXT", maxLength: 100, nullable: false),
                    Description = table.Column<string>(type: "TEXT", maxLength: 500, nullable: false),
                    SystemPrompt = table.Column<string>(type: "TEXT", nullable: false),
                    UserPrompt = table.Column<string>(type: "TEXT", nullable: false),
                    Model = table.Column<string>(type: "TEXT", maxLength: 160, nullable: false),
                    Temperature = table.Column<double>(type: "REAL", nullable: false),
                    MaxOutputTokens = table.Column<int>(type: "INTEGER", nullable: false),
                    MaxIterations = table.Column<int>(type: "INTEGER", nullable: false),
                    MaxToolOutputCharacters = table.Column<int>(type: "INTEGER", nullable: false),
                    IsEnabled = table.Column<bool>(type: "INTEGER", nullable: false),
                    CreatedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    UpdatedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_JobDefinitions", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_JobDefinitions_Name",
                table: "JobDefinitions",
                column: "Name");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "JobDefinitions");
        }
    }
}
