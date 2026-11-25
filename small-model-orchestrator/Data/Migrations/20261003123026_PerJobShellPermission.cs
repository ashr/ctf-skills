using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace smallmodelorchestrator.Data.Migrations
{
    /// <inheritdoc />
    public partial class PerJobShellPermission : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<bool>(
                name: "AllowShellTools",
                table: "JobDefinitions",
                type: "INTEGER",
                nullable: false,
                defaultValue: false);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AllowShellTools",
                table: "JobDefinitions");
        }
    }
}
