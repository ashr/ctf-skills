using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace smallmodelorchestrator.Data.Migrations
{
    /// <inheritdoc />
    public partial class PersistentRuns : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "JobRuns",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    JobDefinitionId = table.Column<int>(type: "INTEGER", nullable: false),
                    JobName = table.Column<string>(type: "TEXT", maxLength: 100, nullable: false),
                    Model = table.Column<string>(type: "TEXT", maxLength: 160, nullable: false),
                    InputText = table.Column<string>(type: "TEXT", nullable: false),
                    PromptSnapshotJson = table.Column<string>(type: "TEXT", nullable: false),
                    Status = table.Column<string>(type: "TEXT", maxLength: 20, nullable: false),
                    Result = table.Column<string>(type: "TEXT", nullable: true),
                    ErrorMessage = table.Column<string>(type: "TEXT", nullable: true),
                    PromptTokens = table.Column<int>(type: "INTEGER", nullable: true),
                    CompletionTokens = table.Column<int>(type: "INTEGER", nullable: true),
                    TotalTokens = table.Column<int>(type: "INTEGER", nullable: true),
                    QueuedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    StartedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: true),
                    CompletedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_JobRuns", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "JobRunEvents",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    JobRunId = table.Column<int>(type: "INTEGER", nullable: false),
                    Kind = table.Column<string>(type: "TEXT", maxLength: 24, nullable: false),
                    Message = table.Column<string>(type: "TEXT", nullable: false),
                    CreatedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_JobRunEvents", x => x.Id);
                    table.ForeignKey(
                        name: "FK_JobRunEvents_JobRuns_JobRunId",
                        column: x => x.JobRunId,
                        principalTable: "JobRuns",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RunArtifacts",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    JobRunId = table.Column<int>(type: "INTEGER", nullable: false),
                    Name = table.Column<string>(type: "TEXT", maxLength: 200, nullable: false),
                    MediaType = table.Column<string>(type: "TEXT", maxLength: 120, nullable: false),
                    Content = table.Column<byte[]>(type: "BLOB", nullable: false),
                    CreatedAtUtc = table.Column<DateTime>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RunArtifacts", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RunArtifacts_JobRuns_JobRunId",
                        column: x => x.JobRunId,
                        principalTable: "JobRuns",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_JobRunEvents_JobRunId",
                table: "JobRunEvents",
                column: "JobRunId");

            migrationBuilder.CreateIndex(
                name: "IX_JobRuns_Status_QueuedAtUtc",
                table: "JobRuns",
                columns: new[] { "Status", "QueuedAtUtc" });

            migrationBuilder.CreateIndex(
                name: "IX_RunArtifacts_JobRunId",
                table: "RunArtifacts",
                column: "JobRunId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "JobRunEvents");

            migrationBuilder.DropTable(
                name: "RunArtifacts");

            migrationBuilder.DropTable(
                name: "JobRuns");
        }
    }
}
