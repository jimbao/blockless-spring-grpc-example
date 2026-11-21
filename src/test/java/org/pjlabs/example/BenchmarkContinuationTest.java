package org.pjlabs.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.TimeUnit;
import net.devh.boot.grpc.client.inject.GrpcClient;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.pjlabs.example.db.ProductRepository;
import org.pjlabs.example.proto.BenchmarkRequest;
import org.pjlabs.example.proto.BenchmarkServiceGrpc;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(
    properties = {
      "grpc.server.inProcessName=test",
      "grpc.server.port=-1",
      "grpc.client.inProcess.address=in-process:test"
    })
@Timeout(15)
class BenchmarkContinuationTest {
  @GrpcClient("inProcess")
  private BenchmarkServiceGrpc.BenchmarkServiceFutureStub benchmark;

  @Autowired private ProductRepository products;
  @Autowired private JdbcTemplate jdbc;

  @Test
  void continuationReturnsTheSameDatabaseResultAsTheExistingModes() throws Exception {
    final var expected = products.countByCountry("SE");
    for (final var mode : new String[] {"join", "blockless", "continuation"}) {
      for (final var thread : new String[] {"pt", "vt"}) {
        final var reply =
            benchmark
                .withDeadlineAfter(5, TimeUnit.SECONDS)
                .query(request(mode, thread, 0.001))
                .get(5, TimeUnit.SECONDS);
        assertEquals(expected, reply.getResult());
        assertEquals("continuation".equals(mode) || "vt".equals(thread), reply.getVirtualThread());
      }
    }
  }

  @Test
  void onePlatformWorkerCanAnswerAnotherRpcWhileTheFirstWaitsInPostgres() throws Exception {
    final var slow =
        benchmark.withDeadlineAfter(6, TimeUnit.SECONDS).query(request("continuation", "pt", 2.0));
    final var deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
    while (System.nanoTime() < deadline && !postgresIsSleeping()) {
      Thread.sleep(10);
    }
    assertTrue(postgresIsSleeping(), "slow query must be waiting in the real database");
    try {
      final var fast =
          benchmark
              .withDeadlineAfter(1, TimeUnit.SECONDS)
              .query(request("continuation", "pt", 0.001))
              .get(1, TimeUnit.SECONDS);
      assertEquals(products.countByCountry("SE"), fast.getResult());
      assertTrue(fast.getVirtualThread());
      assertFalse(slow.isDone(), "fast RPC must finish before the slow database query");
    } finally {
      slow.get(6, TimeUnit.SECONDS);
    }
  }

  private boolean postgresIsSleeping() {
    return Boolean.TRUE.equals(
        jdbc.queryForObject(
            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE wait_event = 'PgSleep' "
                + "AND query LIKE '%products%' AND query LIKE '%pg_sleep%')",
            Boolean.class));
  }

  private static BenchmarkRequest request(String mode, String thread, double sleep) {
    return BenchmarkRequest.newBuilder()
        .setMode(mode)
        .setThreadType(thread)
        .setCountry("SE")
        .setSleepSeconds(sleep)
        .setPtPoolSize(1)
        .setDbPoolSize(10)
        .build();
  }
}
