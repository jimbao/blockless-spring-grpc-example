package org.pjlabs.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.zaxxer.hikari.HikariDataSource;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.pjlabs.example.db.ProductRepository;
import org.pjlabs.example.proto.BenchmarkReply;
import org.pjlabs.example.proto.BenchmarkRequest;

class BenchmarkFailureTest {
  @Test
  void asynchronousQueryFailureReachesTheClientInsteadOfLeavingTheRpcOpen() throws Exception {
    final var products = mock(ProductRepository.class);
    when(products.countByCountryWithDelay(anyString(), anyDouble()))
        .thenThrow(new IllegalStateException("database unavailable"));
    final var failure = new CompletableFuture<Throwable>();
    try (final var dataSource = new HikariDataSource()) {
      final var service = new BenchmarkGrpcService(products, dataSource);
      service.query(
          BenchmarkRequest.newBuilder()
              .setMode("continuation")
              .setThreadType("pt")
              .setPtPoolSize(1)
              .build(),
          new StreamObserver<>() {
            @Override
            public void onNext(BenchmarkReply value) {
              failure.completeExceptionally(new AssertionError("unexpected result"));
            }

            @Override
            public void onError(Throwable error) {
              failure.complete(error);
            }

            @Override
            public void onCompleted() {
              failure.completeExceptionally(new AssertionError("unexpected success"));
            }
          });
      final var error = failure.get(5, TimeUnit.SECONDS);
      assertEquals(Status.Code.INTERNAL, Status.fromThrowable(error).getCode());
      assertInstanceOf(IllegalStateException.class, error.getCause());
    }
  }
}
